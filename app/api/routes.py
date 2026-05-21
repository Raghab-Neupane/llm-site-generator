from fastapi import APIRouter
from fastapi.responses import FileResponse

from pydantic import BaseModel

from app.crawler.robots_parser import (
    parse_robots
)

from app.crawler.sitemap_parser import (
    parse_sitemap
)

from app.crawler.internal_link_extractor import (
    extract_internal_links
)

from app.extractor.html_fetcher import (
    fetch_html
)

from app.transformer.markdown_generator import (
    generate_markdown
)

from app.transformer.llms_generator import (
    generate_llms_txt
)

from app.storage.file_writer import (
    save_llms_txt
)

def normalize_url(url: str) -> str:
    """Normalize a URL to prevent duplicates (lowercase hostname, strip slash, strip query/fragment)."""
    if not url:
        return ""
    url = url.strip()
    if "#" in url:
        url = url.split("#")[0]
    if "?" in url:
        url = url.split("?")[0]
    return url.rstrip("/")


def is_valid_url(url: str) -> bool:
    """Filter out non-http, query/fragment loops, and unwanted pages (admin, login, 404, etc)."""
    if not url:
        return False
    
    url_lower = url.lower()
    
    # Must start with http:// or https://
    if not (url_lower.startswith("http://") or url_lower.startswith("https://")):
        return False
        
    # Skip mailto, javascript, anchor fragments
    if "mailto:" in url_lower or "javascript:" in url_lower or "#" in url_lower:
        return False
        
    # Bad path patterns to skip
    bad_patterns = [
        "/404", "/login", "/signup", "/cart", "/password", "/admin", 
        "/ssa", "/wp-admin", "/wp-content", "/wp-includes"
    ]
    for pattern in bad_patterns:
        if pattern in url_lower:
            return False
            
    # Skip obvious binary files or media if they slip through
    bad_extensions = (
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
        ".pdf", ".zip", ".tar", ".gz", ".css", ".js", ".xml", ".json"
    )
    if url_lower.endswith(bad_extensions):
        return False
        
    return True


def get_url_score(url: str, base_url: str) -> int:
    """Score URLs to prioritize high quality pages like /docs, /blog, /pricing, and the homepage."""
    normalized = normalize_url(url)
    normalized_base = normalize_url(base_url)
    
    if normalized == normalized_base:
        return 100  # Homepage is highest priority
        
    url_lower = normalized.lower()
    
    # Check for high quality keywords
    high_quality_patterns = ["/about", "/docs", "/blog", "/pricing", "/legal", "/api"]
    for pattern in high_quality_patterns:
        if pattern in url_lower:
            return 50
            
    return 0


router = APIRouter()


class CrawlRequest(BaseModel):
    url: str


@router.post("/crawl-site")
async def crawl_site(request: CrawlRequest):

    # STEP 1
    # PARSE ROBOTS.TXT

    robots_data = await parse_robots(
        request.url
    )

    sitemap_urls = robots_data[
        "sitemap_urls"
    ]

    actual_pages = []
    sitemap_data = None
    crawl_method = "sitemap"

    # STEP 2
    # TRY SITEMAP FLOW

    if sitemap_urls:

        sitemap_data = await parse_sitemap(
            sitemap_urls[0]
        )

        actual_pages = sitemap_data[
            "actual_pages"
        ]

        # HANDLE NESTED SITEMAPS

        if not actual_pages:

            nested_sitemaps = sitemap_data.get(
                "sitemaps",
                []
            )

            for nested_sitemap in nested_sitemaps[:3]:

                nested_data = await parse_sitemap(
                    nested_sitemap
                )

                nested_pages = nested_data.get(
                    "actual_pages",
                    []
                )

                actual_pages.extend(
                    nested_pages
                )

    # STEP 2B
    # FALLBACK: EXTRACT LINKS FROM HOMEPAGE

    if not actual_pages:

        crawl_method = "homepage_extraction"

        link_data = await extract_internal_links(
            request.url,
            max_links=15
        )

        actual_pages = link_data.get(
            "links",
            []
        )

    # STEP 2C
    # DEDUPLICATE, FILTER, AND PRIORITIZE CANDIDATE PAGES

    # Start with the homepage itself as a candidate
    candidate_urls = [request.url]
    candidate_urls.extend(actual_pages)

    # Filter out invalid, low quality, and duplicate URLs
    seen = set()
    unique_urls = []
    for url in candidate_urls:
        normalized = normalize_url(url)
        if is_valid_url(url) and normalized not in seen:
            seen.add(normalized)
            unique_urls.append(url)

    # Sort URLs based on priority (Homepage first, followed by key pages like about, docs, pricing, etc.)
    unique_urls.sort(key=lambda u: get_url_score(u, request.url), reverse=True)

    # STILL NO PAGES
    if not unique_urls:

        return {
            "status": "error",
            "message": "No pages found via sitemap or homepage links after filtering"
        }

    # STEP 3
    # FETCH PAGES AND SELECT HIGH QUALITY CONTENT

    pages_data = []
    MAX_PAGES = 5  # Keep up to 5 best quality pages

    for page_url in unique_urls:
        if len(pages_data) >= MAX_PAGES:
            break

        try:

            html = await fetch_html(
                page_url
            )

            markdown = generate_markdown(
                html,
                page_url
            )

            title = (
                markdown
                .split("\n")[0]
                .replace("#", "")
                .strip()
            )

            # Skip pages with missing/generic titles, empty content, or extremely short markdown
            if (
                not title 
                or title.lower() in ("no title", "", "untitled") 
                or not markdown.strip() 
                or len(markdown.strip()) < 150
            ):
                continue

            pages_data.append({
                "title": title,
                "url": page_url,
                "markdown": markdown,
                "description": (
                    markdown[:150]
                    if markdown else
                    "No description"
                )
            })

        except Exception as e:

            print(
                f"Error processing {page_url}: {e}"
            )

    # STEP 4
    # GENERATE SITE NAME

    site_name = (
        request.url
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
        .split("/")[0]
        .split(".")[0]
        .capitalize()
    )

    # STEP 5
    # GENERATE LLMS.TXT

    llms_txt = generate_llms_txt(
        site_name,
        pages_data
    )

    # STEP 6
    # SAVE FILE

    save_llms_txt(llms_txt)

    # STEP 7
    # RETURN RESPONSE

    return {
        "status": "success",
        "crawl_method": crawl_method,
        "robots": robots_data,
        "sitemap": sitemap_data,
        "total_pages_processed": len(
            pages_data
        ),
        "llms_txt_preview": llms_txt[:5000]
    }


@router.get("/llms.txt")
async def get_llms_txt():

    return FileResponse(
        path="outputs/llms.txt",
        media_type="text/plain",
        filename="llms.txt"
    )