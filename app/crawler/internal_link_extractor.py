import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Optional

# FILE EXTENSIONS TO SKIP
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".ico", ".webp", ".avif",
    ".pdf", ".zip", ".tar", ".gz",
    ".css", ".js", ".map",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mp3", ".avi", ".mov",
    ".xml", ".json", ".rss",
}

# PATH SEGMENTS TO SKIP
SKIP_PATHS = {
    "/wp-content/",
    "/wp-admin/",
    "/wp-includes/",
    "/assets/",
    "/static/",
    "/media/",
    "/cdn-cgi/",
    "/login",
    "/signup",
    "/signin",
    "/register",
    "/logout",
    "/auth",
    "/cart",
    "/checkout",
    "/password",
    "/admin",
}

# SOCIAL / EXTERNAL DOMAINS TO SKIP
SKIP_DOMAINS = {
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "github.com",
    "t.co",
}

def _should_skip_url(url: str) -> bool:
    if url.startswith(("mailto:", "tel:", "javascript:", "data:", "ftp:", "#")):
        return True

    parsed = urlparse(url)
    path = parsed.path.lower()

    for ext in SKIP_EXTENSIONS:
        if path.endswith(ext):
            return True

    for skip_path in SKIP_PATHS:
        if skip_path in path:
            return True

    return False

def _is_same_domain(url: str, base_domain: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    return host == base_domain

def _is_social_domain(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    for domain in SKIP_DOMAINS:
        if domain in host:
            return True
    return False

def _normalize_url(href: str, base_url: str) -> Optional[str]:
    if _should_skip_url(href):
        return None
    full_url = urljoin(base_url, href)
    parsed = urlparse(full_url)
    if parsed.scheme not in ("http", "https"):
        return None
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return clean_url.rstrip("/")

def get_link_score(url: str) -> int:
    url_lower = url.lower()
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

async def extract_internal_links(base_url: str, max_links: int = 20) -> dict:
    base_url = base_url.rstrip("/")
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower().replace("www.", "")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            response = await client.get(base_url)
            html = response.text
    except Exception as e:
        return {
            "base_url": base_url,
            "links": [],
            "total_found": 0,
            "error": str(e)
        }

    soup = BeautifulSoup(html, "html.parser")
    all_anchors = soup.find_all("a", href=True)
    seen = set()
    internal_links = []

    for anchor in all_anchors:
        href = anchor["href"].strip()
        if not href:
            continue
        clean_url = _normalize_url(href, base_url)
        if clean_url is None:
            continue
        if not _is_same_domain(clean_url, base_domain):
            continue
        if _is_social_domain(clean_url):
            continue
        if clean_url == base_url:
            continue
        if clean_url in seen:
            continue
        seen.add(clean_url)
        internal_links.append(clean_url)

    # Sort links based on score so the best pages are processed first
    internal_links.sort(key=get_link_score, reverse=True)

    return {
        "base_url": base_url,
        "links": internal_links[:max_links],
        "total_found": len(internal_links),
        "method": "homepage_link_extraction"
    }
