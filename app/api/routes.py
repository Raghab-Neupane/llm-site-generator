from app.extractor.content_analyzer import weak_content
import re
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
async def fetch_spa_html(url: str) -> str:

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        await page.goto(
            url,
            wait_until="networkidle",
            timeout=60000
        )

        html = await page.content()

        await browser.close()

        return html


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
    # Log scores
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

    # STEP 6: FETCH PAGE CONTENT AND EVALUATE QUALITY
    pages_data = []
    MAX_PAGES = 5
    seen_titles = set()
    seen_hashes = set()

    for page_url in unique_urls:
        if len(pages_data) >= MAX_PAGES:
            print(f"[DEBUG] Target limit of {MAX_PAGES} pages reached.")
            break

        try:
            print(f"[DEBUG] Fetching HTML for page: {page_url}")
            html = await fetch_html(page_url)

            if weak_content(html):
               print("[DEBUG] Weak static HTML detected")
               html = await fetch_spa_html(page_url)

            if len(html) > 2_000_000:
                print(f"[DEBUG] Skipped page {page_url} (size {len(html)} bytes exceeds 2MB limit)")
                continue

            # Check link density (navigation/link farm checking)
            soup = BeautifulSoup(html, "html.parser")
            text_all = soup.get_text()
            text_all_len = len(clean_text(text_all))
            text_links = "".join(a.get_text() for a in soup.find_all("a"))
            text_links_len = len(clean_text(text_links))
            
            link_density = text_links_len / text_all_len if text_all_len > 0 else 0
            if link_density > 0.5:
                print(f"[DEBUG] Skipped page {page_url} due to high link density ({link_density:.2f})")
                continue

            # Convert to Markdown
            markdown = generate_markdown(html, page_url)
            markdown_len = len(markdown.strip())
            print(f"[DEBUG] Generated Markdown length: {markdown_len}")

            # Quality Check: Skip empty or extremely short content
            if markdown_len < 150:
                print(f"[DEBUG] Skipped page {page_url} due to short markdown length ({markdown_len} chars)")
                continue

            # Quality Check: Check for typical Error Pages or JS Shell Pages in the title
            title = "No Title"
            for line in markdown.splitlines():
                cleaned = line.replace("#", "").strip()
                if cleaned:
                    title = cleaned
                    break

            title_lower = title.lower()
            if title_lower in ["no title", "", "untitled", "404", "not found", "error", "site maintenance", "unauthorized"]:
                print(f"[DEBUG] Skipped page {page_url} due to generic/error title: '{title}'")
                continue

            # Deduplication based on title or content hash (first 200 chars normalized)
            title_norm = re.sub(r'\W+', '', title).lower()
            content_hash = re.sub(r'\W+', '', markdown[:200]).lower()
            
            if title_norm in seen_titles:
                print(f"[DEBUG] Skipped duplicate page by title: '{title}' ({page_url})")
                continue
            if content_hash in seen_hashes:
                print(f"[DEBUG] Skipped duplicate page by content hash: {page_url}")
                continue

            seen_titles.add(title_norm)
            seen_hashes.add(content_hash)

            # Description Extraction
            description = clean_description(markdown)
            print(f"[DEBUG] Extracted description: '{description}'")

            pages_data.append({
                "title": title,
                "url": page_url,
                "markdown": markdown,
                "description": description
            })
            print(f"[DEBUG] Successfully added page: '{title}'")

        except Exception as e:
            print(f"[DEBUG] Error processing {page_url}: {e}")

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