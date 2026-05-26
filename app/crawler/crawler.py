import logging
import asyncio
import re
from urllib.parse import urlparse, urljoin
import httpx

from app.crawler.robots import RobotsParser
from app.crawler.sitemap import SitemapParser
from app.crawler.ranker import URLRanker
from app.crawler.extractor import PageExtractor
from app.detector.detector import detect_page_type
from app.spa.renderer import SPARenderer
from app.spa.extractor import SPAExtractor

logger = logging.getLogger("crawler.crawler")

class SemanticCrawler:
    """
    A production-grade, highly intelligent website crawling engine.
    Orchestrates sitemap parsing, robots checking, priority link queues, 
    multi-signal weighted SPA classification, and a professional escalation pipeline
    that falls back on Playwright dynamic rendering if static content is weak.
    """
    def __init__(self, concurrency_limit: int = 3):
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        self.client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Googlebot/2.1; +http://www.google.com/bot.html)"},
            timeout=15.0,
            follow_redirects=True
        )
        self.robots_parser = RobotsParser(self.client)
        self.sitemap_parser = SitemapParser(self.client)
        self.ranker = URLRanker()
        self.spa_renderer = SPARenderer()

    def is_weak_content(self, text: str, html: str) -> bool:
        """
        Applies strict heuristics to verify if extracted static contents 
        are weak or represent unhydrated framework placeholders.
        """
        # 1. Very shallow visible contents
        if len(text.strip()) < 150:
            return True
            
        # 2. Presence of raw template double brackets
        if "{{" in text or "{{" in html:
            return True
            
        # 3. Presence of common Angular/Vue template attributes leaking into visible DOM
        if any(term in html for term in ["v-if", "ng-if", "ng-repeat", "v-for"]):
            return True
            
        return False

    async def _fetch_and_evaluate(self, url: str, progress_callback=None, force_spa=False) -> tuple[str, str, bool]:
        """
        Fetches the URL statically first, runs classification, 
        and assesses if we should escalate to dynamic SPA rendering.
        
        Returns (html, method_used, was_escalated)
        """
        async with self.semaphore:
            logger.info(f"[CRAWLER] Visiting URL: {url}")
            if progress_callback:
                await progress_callback(f"[CRAWLER] Visiting URL: {url}")
                
            if force_spa:
                if progress_callback:
                    await progress_callback("[DETECTOR] Escalating to SPA renderer")
                logger.info(f"Forcing SPA rendering due to sitemap fallback context: {url}")
                rendered_html = await self.spa_renderer.render(url, progress_callback=progress_callback)
                return rendered_html, "spa", True

            try:
                # 1. Native HTTPX get
                response = await self.client.get(url, timeout=12.0)
                if response.status_code != 200:
                    logger.warning(f"Static request failed with status code {response.status_code} for {url}")
                    return "", "static", False

                html = response.text
                
                # 2. Weighted SPA detection
                if progress_callback:
                    await progress_callback("[DETECTOR] Checking SPA signals")
                page_type = detect_page_type(html)
                
                if page_type == "spa":
                    logger.info(f"Classified as SPA. Routing via SPARenderer: {url}")
                    if progress_callback:
                        await progress_callback("[DETECTOR] Escalating to SPA renderer")
                    rendered_html = await self.spa_renderer.render(url, progress_callback=progress_callback)
                    return rendered_html, "spa", False
                    
                # 3. Quality evaluation check (Detecting unhydrated static pages)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                visible_text = soup.get_text()
                
                if self.is_weak_content(visible_text, html):
                    logger.info(f"[DETECTOR] Escalating to SPA renderer for: {url}")
                    if progress_callback:
                        await progress_callback("[DETECTOR] Escalating to SPA renderer")
                    rendered_html = await self.spa_renderer.render(url, progress_callback=progress_callback)
                    return rendered_html, "spa", True

                return html, "static", False

            except Exception as e:
                logger.warning(f"Static fetch failed for {url}: {e}. Escalating to SPARenderer fallback...")
                try:
                    if progress_callback:
                        await progress_callback("[DETECTOR] Escalating to SPA renderer")
                    rendered_html = await self.spa_renderer.render(url, progress_callback=progress_callback)
                    return rendered_html, "spa", True
                except Exception as ex:
                    logger.critical(f"All rendering pathways failed for {url}: {ex}")
                    return "", "failed", False

    async def crawl(self, start_url: str, max_pages: int = 15, max_depth: int = 3, progress_callback=None) -> dict:
        """
        Orchestrates semantic crawling across the target domain, adhering 
        to Robots rules, scanning Sitemaps recursively, and queueing links BFS.
        """
        start_url = self.ranker.normalize_url(start_url)
        parsed_start = urlparse(start_url)
        base_host = parsed_start.netloc.lower()

        logger.info(f"=== Starting Professional Semantic Crawl for: {start_url} ===")

        # 1. Robots check
        if not await self.robots_parser.can_fetch(start_url):
            logger.error(f"Crawl disallowed by robots.txt directives for: {start_url}")
            return {
                "status": "error",
                "message": "Crawl disallowed by robots.txt rules"
            }

        # 2. Sitemap Discovery
        logger.info("[CRAWLER] Parsing sitemap")
        if progress_callback:
            await progress_callback("[CRAWLER] Parsing sitemap")
            
        sitemap_urls = await self.robots_parser.get_sitemaps(start_url)
        if not sitemap_urls:
            sitemap_urls = [
                f"{parsed_start.scheme}://{parsed_start.netloc}/sitemap.xml",
                f"{parsed_start.scheme}://{parsed_start.netloc}/sitemap_index.xml"
            ]

        discovered_urls = []
        for s_url in sitemap_urls:
            parsed_urls = await self.sitemap_parser.parse_sitemap(s_url)
            discovered_urls.extend(parsed_urls)

        # Automatic SPA Fallback on sitemap fail
        force_spa = False
        if not discovered_urls:
            logger.info("Sitemap discovery returned 0 URLs. Automatically escalating to SPA dynamic rendering path!")
            force_spa = True
            if progress_callback:
                await progress_callback("[CRAWLER] Sitemap failed")
                await progress_callback("[CRAWLER] Escalating to SPA renderer")

        # 3. BFS Setup
        queue = []
        visited = set()

        if discovered_urls:
            logger.info(f"Seeding crawl queue with {len(discovered_urls)} URLs found in sitemaps")
            for url in discovered_urls:
                norm_u = self.ranker.normalize_url(url)
                if self.ranker.is_valid_url(norm_u, base_host) and norm_u not in visited:
                    queue.append((norm_u, 1))

        if start_url not in visited:
            queue.insert(0, (start_url, 0))

        pages_data = []
        seen_titles = set()
        seen_content_hashes = set()
        total_attempts = 0
        crawl_method_tally = {"static": 0, "spa": 0}

        static_extractor = PageExtractor(start_url)
        spa_extractor = SPAExtractor(start_url)

        # BFS Crawl Execution Loop
        while queue and len(pages_data) < max_pages and total_attempts < max_pages * 3:
            # Sort queue: primary by depth (ascending), secondary by URL rank priority (descending)
            queue.sort(key=lambda x: (x[1], -self.ranker.calculate_priority(x[0])))

            current_url, depth = queue.pop(0)

            if depth > max_depth:
                continue

            if current_url in visited:
                continue
            visited.add(current_url)
            total_attempts += 1

            # Fetch HTML with dynamic classification & escalation
            html, method, escalated = await self._fetch_and_evaluate(current_url, progress_callback=progress_callback, force_spa=force_spa)
            if not html:
                continue

            crawl_method_tally[method] = crawl_method_tally.get(method, 0) + 1

            # Select extractor depending on method used
            extractor = spa_extractor if method == "spa" else static_extractor

            try:
                page_info = extractor.extract(html, current_url)
                if not page_info or not page_info["markdown"].strip():
                    continue

                # Title and Content Deduplication
                title = page_info["title"]
                title_norm = re.sub(r'\W+', '', title).lower()
                content_hash = re.sub(r'\W+', '', page_info["markdown"][:150]).lower()

                if any(err in title_norm for err in ["404", "notfound", "error", "unauthorized", "maintenance"]):
                    logger.info(f"Skipping page due to error signature: '{title}'")
                    continue

                if title_norm in seen_titles:
                    logger.info(f"Skipped duplicate page by title check: '{title}'")
                    continue
                if content_hash in seen_content_hashes:
                    logger.info("Skipped duplicate page by content hash.")
                    continue

                seen_titles.add(title_norm)
                seen_content_hashes.add(content_hash)

                pages_data.append(page_info)
                logger.info(f"Successfully processed page [{len(pages_data)}/{max_pages}]: '{title}' ({current_url})")

                # Discover new links recursively
                if depth < max_depth:
                    for link_obj in page_info["assets"]["links"]:
                        if link_obj["is_internal"]:
                            norm_lnk = self.ranker.normalize_url(link_obj["url"])
                            if self.ranker.is_valid_url(norm_lnk, base_host) and norm_lnk not in visited:
                                queue.append((norm_lnk, depth + 1))

            except Exception as ex:
                logger.error(f"Error parsing page {current_url}: {ex}", exc_info=True)

        # Clean up browser
        await self.spa_renderer.shutdown()

        dominant_method = "spa" if crawl_method_tally.get("spa", 0) > crawl_method_tally.get("static", 0) else "static"

        return {
            "status": "success",
            "crawl_method": dominant_method,
            "total_pages_processed": len(pages_data),
            "pages": pages_data
        }
