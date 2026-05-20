from typing import Optional

import httpx
from bs4 import BeautifulSoup
from urllib.parse import (
    urljoin,
    urlparse
)

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
    """Check if a URL should be skipped
    based on extension, path, or scheme."""

    # SKIP NON-HTTP SCHEMES

    if url.startswith((
        "mailto:", "tel:",
        "javascript:", "data:",
        "ftp:", "#"
    )):
        return True

    parsed = urlparse(url)
    path = parsed.path.lower()

    # SKIP FILE EXTENSIONS

    for ext in SKIP_EXTENSIONS:

        if path.endswith(ext):
            return True

    # SKIP ASSET PATHS

    for skip_path in SKIP_PATHS:

        if skip_path in path:
            return True

    return False


def _is_same_domain(
    url: str,
    base_domain: str
) -> bool:
    """Check if a URL belongs to the
    same domain as the base URL."""

    parsed = urlparse(url)

    host = parsed.netloc.lower()

    # REMOVE www. PREFIX

    host = host.replace("www.", "")

    return host == base_domain


def _is_social_domain(url: str) -> bool:
    """Check if a URL points to a
    social media domain."""

    parsed = urlparse(url)

    host = parsed.netloc.lower()

    for domain in SKIP_DOMAINS:

        if domain in host:
            return True

    return False


def _normalize_url(
    href: str,
    base_url: str
) -> Optional[str]:
    """Normalize a relative or absolute
    URL into a clean absolute URL."""

    if _should_skip_url(href):
        return None

    # RESOLVE RELATIVE URLS

    full_url = urljoin(base_url, href)

    parsed = urlparse(full_url)

    # ONLY ALLOW HTTP/HTTPS

    if parsed.scheme not in ("http", "https"):
        return None

    # REMOVE FRAGMENT AND QUERY

    clean_url = (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
    )

    # REMOVE TRAILING SLASH

    clean_url = clean_url.rstrip("/")

    return clean_url


async def extract_internal_links(
    base_url: str,
    max_links: int = 15
) -> dict:
    """Fetch homepage HTML and extract
    unique internal links.

    Args:
        base_url: The website homepage URL.
        max_links: Maximum links to return.

    Returns:
        Dictionary with extracted links
        and metadata.
    """

    base_url = base_url.rstrip("/")

    parsed_base = urlparse(base_url)

    base_domain = (
        parsed_base.netloc
        .lower()
        .replace("www.", "")
    )

    # FETCH HOMEPAGE

    try:

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0
        ) as client:

            response = await client.get(
                base_url
            )

            html = response.text

    except Exception as e:

        return {
            "base_url": base_url,
            "links": [],
            "total_found": 0,
            "error": str(e)
        }

    # PARSE HTML

    soup = BeautifulSoup(html, "html.parser")

    # EXTRACT ALL <a> TAGS

    all_anchors = soup.find_all(
        "a",
        href=True
    )

    seen = set()
    internal_links = []

    for anchor in all_anchors:

        href = anchor["href"].strip()

        if not href:
            continue

        # NORMALIZE

        clean_url = _normalize_url(
            href,
            base_url
        )

        if clean_url is None:
            continue

        # SKIP EXTERNAL DOMAINS

        if not _is_same_domain(
            clean_url,
            base_domain
        ):
            continue

        # SKIP SOCIAL LINKS

        if _is_social_domain(clean_url):
            continue

        # SKIP HOMEPAGE ITSELF

        if clean_url == base_url:
            continue

        # SKIP DUPLICATES

        if clean_url in seen:
            continue

        seen.add(clean_url)

        internal_links.append(clean_url)

        # STOP AT LIMIT

        if len(internal_links) >= max_links:
            break

    return {
        "base_url": base_url,
        "links": internal_links,
        "total_found": len(internal_links),
        "method": "homepage_link_extraction"
    }
