import logging
import httpx
import gzip
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

logger = logging.getLogger("crawler.sitemap")

class SitemapParser:
    """
    An intelligent XML Sitemap parser that recursively processes standard sitemaps, 
    nested sitemap indexes, and compressed (.gz) sitemaps.
    """
    def __init__(self, client: httpx.AsyncClient = None):
        self.client = client or httpx.AsyncClient(timeout=15.0)

    async def parse_sitemap(self, sitemap_url: str, max_depth: int = 3, current_depth: int = 1) -> list[str]:
        """
        Recursively fetches and parses sitemaps or sitemap indexes.
        Returns a list of clean URLs discovered.
        """
        if current_depth > max_depth:
            logger.warning(f"Sitemap recursion limit reached for {sitemap_url}")
            return []

        logger.info(f"Parsing sitemap URL [depth={current_depth}]: {sitemap_url}")
        urls = []
        
        try:
            response = await self.client.get(sitemap_url, follow_redirects=True)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch sitemap: {sitemap_url} (status={response.status_code})")
                return []

            content = response.content
            # Handle compressed sitemap if .gz extension or header matches
            if sitemap_url.lower().endswith(".gz") or content.startswith(b"\x1f\x8b"):
                logger.info(f"Decompressing Gzipped sitemap: {sitemap_url}")
                try:
                    content = gzip.decompress(content)
                except Exception as ex:
                    logger.error(f"Gzip decompression failed for sitemap {sitemap_url}: {ex}")
                    return []

            # Parse XML tree
            root = ET.fromstring(content)
            
            # Namespace stripping / standard extraction
            # XML elements can have namespaces like "{http://www.sitemaps.org/schemas/sitemap/0.9}"
            namespace = ""
            if root.tag.startswith("{"):
                namespace = root.tag.split("}")[0] + "}"

            # 1. Sitemap Index (contains other sitemaps)
            if root.tag == f"{namespace}sitemapindex":
                logger.info(f"Detected sitemap index file at {sitemap_url}. Recursing...")
                for sitemap_node in root.findall(f"{namespace}sitemap"):
                    loc_node = sitemap_node.find(f"{namespace}loc")
                    if loc_node is not None and loc_node.text:
                        sub_urls = await self.parse_sitemap(
                            loc_node.text.strip(), 
                            max_depth=max_depth, 
                            current_depth=current_depth + 1
                        )
                        urls.extend(sub_urls)

            # 2. Standard Sitemap (contains page locations)
            elif root.tag == f"{namespace}urlset":
                for url_node in root.findall(f"{namespace}url"):
                    loc_node = url_node.find(f"{namespace}loc")
                    if loc_node is not None and loc_node.text:
                        urls.append(loc_node.text.strip())

        except ET.ParseError as e:
            logger.error(f"Sitemap XML parsing error at {sitemap_url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing sitemap at {sitemap_url}: {e}", exc_info=True)
            
        logger.info(f"Extracted {len(urls)} URLs from sitemap: {sitemap_url}")
        return urls
