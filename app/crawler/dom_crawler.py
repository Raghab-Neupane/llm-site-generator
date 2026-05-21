from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import httpx
from typing import List

# Import normalizer and filter rules from link extractor to avoid divergence
from app.crawler.internal_link_extractor import _normalize_url, _is_same_domain, _is_social_domain, get_link_score

async def crawl_from_dom(base_url: str):
    discovered_links = []
    base_url = base_url.rstrip("/")
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower().replace("www.", "")

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0
        ) as client:
            response = await client.get(base_url)
            html = response.text
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "links": []
        }

    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    seen = set()

    for anchor in anchors:
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
        discovered_links.append(clean_url)

    # Sort links based on quality score
    discovered_links.sort(key=get_link_score, reverse=True)

    return {
        "status": "success",
        "total_links": len(discovered_links),
        "links": discovered_links[:20]
    }