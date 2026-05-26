import logging
import httpx
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger("crawler.robots")

class RobotsParser:
    """
    A robust robots.txt parsing and caching manager that respects site crawl directives.
    Uses urllib.robotparser under the hood for standards compliance.
    """
    def __init__(self, client: httpx.AsyncClient = None):
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self._cache = {}  # Map domain (scheme + netloc) -> RobotFileParser

    def _get_robots_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    async def _fetch_and_parse(self, url: str) -> RobotFileParser:
        domain = self._get_robots_url(url)
        if domain in self._cache:
            return self._cache[domain]

        parser = RobotFileParser()
        robots_txt_url = f"{domain}"
        logger.info(f"Fetching robots.txt rules from: {robots_txt_url}")
        
        try:
            response = await self.client.get(robots_txt_url)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
                logger.info(f"Successfully loaded and parsed robots.txt for {domain}")
            else:
                # Allow all if robots.txt doesn't exist
                logger.debug(f"robots.txt status {response.status_code} for {domain}, default allow all")
                parser.parse(["User-agent: *", "Allow: /"])
        except Exception as e:
            logger.warning(f"Failed to fetch robots.txt from {robots_txt_url}: {e}. Falling back to default allow all.")
            parser.parse(["User-agent: *", "Allow: /"])
            
        self._cache[domain] = parser
        return parser

    async def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        """Determines if the crawler is allowed to crawl the specified URL."""
        try:
            parser = await self._fetch_and_parse(url)
            return parser.can_fetch(user_agent, url)
        except Exception as e:
            logger.warning(f"Error checking robots rules for {url}: {e}. Defaulting to True.")
            return True

    async def get_sitemaps(self, url: str) -> list[str]:
        """Extracts any sitemap URLs declared in robots.txt."""
        try:
            parser = await self._fetch_and_parse(url)
            sitemaps = parser.sitemaps
            return sitemaps if sitemaps else []
        except Exception as e:
            logger.warning(f"Error reading sitemap listings from robots.txt of {url}: {e}")
            return []
