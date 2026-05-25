from app.extractor.content_analyzer import weak_content
import re
import json
import datetime
from pathlib import Path
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from playwright.async_api import async_playwright

from app.crawler.robots_parser import parse_robots
from app.crawler.sitemap_parser import parse_sitemap
from app.crawler.internal_link_extractor import extract_internal_links
from app.extractor.html_fetcher import fetch_html
from app.transformer.markdown_generator import generate_markdown
from app.transformer.llms_generator import generate_llms_txt
from app.storage.file_writer import save_llms_txt
from app.api.authentication.dependencies import verify_token

router = APIRouter()


# ---------------------------------------------------------
# SPA FETCHER — returns visible rendered text only
# ---------------------------------------------------------
async def fetch_spa_html(url: str) -> str:
    """
    Fetch visible rendered text from a SPA page using Playwright.
    Returns inner_text() instead of page.content() so that Angular/React/Vue
    template artifacts (ngRepeat, ngIf, hydration markers, etc.) are excluded.
    """
    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        try:
            page = await browser.new_page()

            print(
                f"[DEBUG] SPA fetch: navigating to {url}"
            )

            # Navigate with domcontentloaded — faster than networkidle
            # and sufficient since we add explicit waits below
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            # Wait for hydration: try to wait for an h1 element
            # which signals the framework has rendered content
            try:
                await page.wait_for_selector(
                    "h1",
                    timeout=8000
                )
                print(
                    "[DEBUG] SPA fetch: h1 selector found"
                )
            except Exception:
                print(
                    "[DEBUG] SPA fetch: h1 not found, "
                    "continuing with stabilization wait"
                )

            # Stabilization wait for remaining hydration / async rendering
            await page.wait_for_timeout(2000)

            # Auto-scroll to trigger lazy-loaded content
            await page.evaluate("""
                async () => {
                    const delay = ms => new Promise(r => setTimeout(r, ms));
                    const scrollHeight = document.body.scrollHeight;
                    const step = Math.max(window.innerHeight, 400);
                    for (let y = 0; y < scrollHeight; y += step) {
                        window.scrollTo(0, y);
                        await delay(300);
                    }
                    window.scrollTo(0, 0);
                }
            """)

            # Brief wait after scrolling for lazy content to settle
            await page.wait_for_timeout(1000)

            # Extract ONLY visible rendered text — no raw DOM / template junk
            text = await page.locator("body").inner_text()

            print(
                f"[DEBUG] SPA fetch: extracted "
                f"{len(text)} chars of visible text"
            )

            return text

        finally:
            await browser.close()


def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()

# -----------------------------
# URL NORMALIZATION
# -----------------------------
def normalize_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if "#" in url:
        url = url.split("#")[0]
    if "?" in url:
        url = url.split("?")[0]
    return url.rstrip("/")

# -----------------------------
# URL FILTERING
# -----------------------------
def is_valid_url(url: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    if not (url_lower.startswith("http://") or url_lower.startswith("https://")):
        return False
    if "mailto:" in url_lower or "javascript:" in url_lower or "#" in url_lower:
        return False

    bad_patterns = [
        "/404", "/login", "/signup", "/cart", "/password", "/admin",
        "/wp-admin", "/wp-content", "/wp-includes", "/auth", "/signin", "/register"
    ]
    for pattern in bad_patterns:
        if pattern in url_lower:
            return False

    bad_extensions = (
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
        ".pdf", ".zip", ".tar", ".gz", ".css", ".js", ".xml", ".json",
        ".mp4", ".mp3", ".avi", ".mov", ".woff", ".woff2", ".ttf", ".eot"
    )
    if url_lower.endswith(bad_extensions):
        return False

    return True

# -----------------------------
# URL PRIORITY SCORING
# -----------------------------
def get_url_score(url: str, base_url: str) -> int:
    normalized = normalize_url(url)
    normalized_base = normalize_url(base_url)

    if normalized == normalized_base:
        return 100  # Homepage gets top priority

    url_lower = normalized.lower()
    score = 0

    high_quality_patterns = {
        "/docs": 90,
        "/api": 85,
        "/guide": 80,
        "/blog": 70,
        "/pricing": 60,
        "/about": 50,
        "/legal": 40,
    }

    for pattern, value in high_quality_patterns.items():
        if pattern in url_lower:
            score += value

    return score

# -----------------------------
# DESCRIPTION EXTRACTION
# -----------------------------
def clean_description(markdown: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip headings, blockquotes, list items
        if line.startswith("#") or line.startswith(">") or line.startswith("*") or line.startswith("-"):
            continue
        # Skip source line if any slips in
        if "source:" in line.lower() or "read more" in line.lower():
            continue
        if len(line) >= 40:
            return line[:200]
    return "No description available"

# -----------------------------
# REQUEST MODEL
# -----------------------------
class CrawlRequest(BaseModel):
    url: str

# -----------------------------
# MAIN CRAWLER ROUTE
# -----------------------------
@router.post("/crawl-site")
async def crawl_site(request: CrawlRequest, payload: dict = Depends(verify_token)):
    print(f"[DEBUG] Received crawl request for base URL: {request.url}")

    # STEP 1: FETCH ROBOTS.TXT
    robots_data = await parse_robots(request.url)
    sitemap_urls = robots_data.get("sitemap_urls", [])
    print(f"[DEBUG] Found {len(sitemap_urls)} sitemap URLs in robots.txt")

    actual_pages = []
    sitemap_data = None
    crawl_method = "sitemap"

    # STEP 2: TRY SITEMAP FLOW
    if sitemap_urls:
        sitemap_data = await parse_sitemap(sitemap_urls[0])
        actual_pages = sitemap_data.get("actual_pages", [])
        print(f"[DEBUG] Found {len(actual_pages)} pages in main sitemap")

        # HANDLE NESTED SITEMAPS
        if not actual_pages:
            nested_sitemaps = sitemap_data.get("sitemaps", [])
            print(f"[DEBUG] Exploring {len(nested_sitemaps)} nested sitemaps")
            for nested_sitemap in nested_sitemaps[:5]:
                nested_data = await parse_sitemap(nested_sitemap)
                nested_pages = nested_data.get("actual_pages", [])
                actual_pages.extend(nested_pages)

    # STEP 3: FALLBACK DOM CRAWLING / HOMEPAGE EXTRACTION
    if not actual_pages:
        crawl_method = "homepage_extraction"
        print(f"[DEBUG] Falling back to homepage DOM internal link extraction")
        link_data = await extract_internal_links(request.url, max_links=20)
        actual_pages = link_data.get("links", [])
        print(f"[DEBUG] Extracted {len(actual_pages)} internal links from homepage")

    # STEP 4: CLEAN + FILTER + DEDUPLICATE URLS
    candidate_urls = [request.url]
    candidate_urls.extend(actual_pages)

    seen = set()
    unique_urls = []
    for url in candidate_urls:
        normalized = normalize_url(url)
        if is_valid_url(url) and normalized not in seen:
            seen.add(normalized)
            unique_urls.append(url)
        elif normalized in seen:
            print(f"[DEBUG] Duplicate URL filtered out: {url}")
        else:
            print(f"[DEBUG] Invalid URL skipped: {url}")

    # STEP 5: PRIORITIZE HIGH QUALITY URLS
    scored_urls = []
    for url in unique_urls:
        score = get_url_score(url, request.url)
        scored_urls.append((url, score))
        print(f"[DEBUG] Scoring URL: {url} -> Score: {score}")

    scored_urls.sort(key=lambda x: x[1], reverse=True)
    unique_urls = [x[0] for x in scored_urls]

    # STILL NO PAGES
    if not unique_urls:
        print(f"[DEBUG] No candidate pages available after filtering")
        return {
            "status": "error",
            "message": "No pages found"
        }

    # -----------------------------
    # STEP 6: FETCH PAGE CONTENT
    # -----------------------------
    pages_data = []
    MAX_PAGES = 5
    seen_titles = set()
    seen_hashes = set()

    for page_url in unique_urls:

        if len(pages_data) >= MAX_PAGES:
            print(
                f"[DEBUG] Target limit of "
                f"{MAX_PAGES} pages reached."
            )
            break

        try:

            print(
                f"[DEBUG] Fetching HTML for page: "
                f"{page_url}"
            )

            # ---------------------------------
            # STATIC FETCH
            # ---------------------------------
            html = await fetch_html(page_url)

            is_spa = False

            # ---------------------------------
            # SPA FALLBACK
            # ---------------------------------
            if weak_content(html):

                print(
                    "[DEBUG] Weak static HTML detected, "
                    "falling back to SPA fetch"
                )

                html = await fetch_spa_html(
                    page_url
                )

                is_spa = True

            # ---------------------------------
            # SIZE CHECK
            # ---------------------------------
            if len(html) > 2_000_000:

                print(
                    f"[DEBUG] Skipped page "
                    f"{page_url} "
                    f"(size {len(html)} "
                    f"bytes exceeds 2MB limit)"
                )

                continue

            # ---------------------------------
            # STATIC HTML FLOW
            # ---------------------------------
            if not is_spa:

                soup = BeautifulSoup(
                    html,
                    "html.parser"
                )

                text_all = soup.get_text()

                text_all_len = len(
                    clean_text(text_all)
                )

                text_links = "".join(
                    a.get_text()
                    for a in soup.find_all("a")
                )

                text_links_len = len(
                    clean_text(text_links)
                )

                link_density = (
                    text_links_len / text_all_len
                    if text_all_len > 0
                    else 0
                )

                if link_density > 0.5:

                    print(
                        f"[DEBUG] Skipped page "
                        f"{page_url} due to "
                        f"high link density "
                        f"({link_density:.2f})"
                    )

                    continue

                markdown = generate_markdown(
                    html,
                    page_url
                )

            # ---------------------------------
            # SPA TEXT FLOW
            # ---------------------------------
            else:

                markdown = f"""
# SPA Content

{html}
"""

            # ---------------------------------
            # MARKDOWN LENGTH CHECK
            # ---------------------------------
            markdown_len = len(
                markdown.strip()
            )

            print(
                f"[DEBUG] Generated Markdown "
                f"length: {markdown_len}"
            )

            if markdown_len < 150:

                print(
                    f"[DEBUG] Skipped page "
                    f"{page_url} due to "
                    f"short markdown length "
                    f"({markdown_len} chars)"
                )

                continue

            # ---------------------------------
            # TITLE EXTRACTION
            # ---------------------------------
            title = "No Title"

            for line in markdown.splitlines():

                cleaned = (
                    line.replace("#", "")
                    .strip()
                )

                if cleaned:
                    title = cleaned
                    break

            title_lower = title.lower()

            if title_lower in [
                "no title",
                "",
                "untitled",
                "404",
                "not found",
                "error",
                "site maintenance",
                "unauthorized"
            ]:

                print(
                    f"[DEBUG] Skipped page "
                    f"{page_url} due to "
                    f"generic/error title: "
                    f"'{title}'"
                )

                continue

            # ---------------------------------
            # DEDUPLICATION
            # ---------------------------------
            title_norm = re.sub(
                r'\W+',
                '',
                title
            ).lower()

            content_hash = re.sub(
                r'\W+',
                '',
                markdown[:200]
            ).lower()

            if title_norm in seen_titles:

                print(
                    f"[DEBUG] Skipped duplicate "
                    f"page by title: "
                    f"'{title}' ({page_url})"
                )

                continue

            if content_hash in seen_hashes:

                print(
                    f"[DEBUG] Skipped duplicate "
                    f"page by content hash: "
                    f"{page_url}"
                )

                continue

            seen_titles.add(title_norm)

            seen_hashes.add(content_hash)

            # ---------------------------------
            # DESCRIPTION EXTRACTION
            # ---------------------------------
            description = clean_description(
                markdown
            )

            print(
                f"[DEBUG] Extracted description: "
                f"'{description}'"
            )

            # ---------------------------------
            # SAVE PAGE DATA
            # ---------------------------------
            pages_data.append({

                "title": title,

                "url": page_url,

                "markdown": markdown,

                "description": description

            })

            print(
                f"[DEBUG] Successfully added "
                f"page: '{title}'"
            )

        except Exception as e:

            print(
                f"[DEBUG] Error processing "
                f"{page_url}: {e}"
            )

    # STEP 7: CHECK CONTENT
    if not pages_data:
        print(f"[DEBUG] Final check: No high quality pages found in pages_data")
        return {
            "status": "error",
            "message": "No high quality pages found"
        }

    # STEP 8: GENERATE SITE NAME
    site_name = (
        request.url
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
        .split("/")[0]
        .split(".")[0]
        .capitalize()
    )

    # STEP 9: GENERATE LLMS.TXT
    llms_txt = generate_llms_txt(site_name, pages_data)

    # STEP 10: SAVE FILE
    save_llms_txt(llms_txt)
    print(f"[DEBUG] Generation completed! llms.txt saved to outputs/llms.txt")

    # Save to history.json
    try:
        history_file = Path("outputs/history.json")
        history_data = []
        if history_file.exists():
            try:
                history_data = json.loads(history_file.read_text())
            except Exception:
                history_data = []

        user_info = payload.get("sub", "anonymous")

        new_item = {
            "url": request.url,
            "title": site_name,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "llms_txt": llms_txt,
            "user": user_info
        }

        # Deduplicate history based on URL and User
        history_data = [item for item in history_data if not (item.get("url") == request.url and item.get("user") == user_info)]
        history_data.insert(0, new_item)

        # Limit history to 50 items
        history_data = history_data[:50]

        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps(history_data, indent=2))
        print(f"[DEBUG] Successfully synced search item to history.json for user: {user_info}")
    except Exception as e:
        print(f"[ERROR] Failed to save search history: {e}")

    # STEP 11: RETURN RESPONSE
    return {
        "status": "success",
        "crawl_method": crawl_method,
        "robots": robots_data,
        "sitemap": sitemap_data,
        "total_pages_processed": len(pages_data),
        "processed_pages": [
            {
                "title": page["title"],
                "url": page["url"]
            }
            for page in pages_data
        ],
        "llms_txt_preview": llms_txt[:5000]
    }


@router.get("/llms.txt")
async def get_llms_txt(payload: dict = Depends(verify_token)):
    return FileResponse(
        path="outputs/llms.txt",
        media_type="text/plain",
        filename="llms.txt"
    )


@router.get("/history")
async def get_history(payload: dict = Depends(verify_token)):
    user_info = payload.get("sub", "anonymous")
    history_file = Path("outputs/history.json")
    if not history_file.exists():
        return []
    try:
        all_history = json.loads(history_file.read_text())
        # Filter history by current user
        user_history = [item for item in all_history if item.get("user") == user_info]
        return user_history
    except Exception:
        return []