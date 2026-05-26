import logging
import asyncio
from playwright.async_api import async_playwright

logger = logging.getLogger("crawler.spa_renderer")

class SPARenderer:
    """
    A professional-grade SPA rendering pipeline using Playwright Chromium.
    Implements advanced progressive scrolling, framework hydration verification, 
    DOM mutation stabilization, and clean visible element extraction.
    """
    def __init__(self):
        self._playwright = None
        self._browser = None

    async def initialize(self):
        """Initializes the persistent browser instance."""
        if not self._browser:
            logger.info("[SPA] Launching browser")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                ]
            )

    async def render(self, url: str, timeout_ms: int = 60000, progress_callback=None) -> str:
        """
        Executes the refined professional SPA rendering flow.
        1. Open URL & Wait domcontentloaded
        2. Wait for framework hydration
        3. progressive auto-scroll down and up
        4. DOM stabilization (mutation checks + text length checks)
        5. Clean Visible DOM harvesting
        """
        if progress_callback:
            await progress_callback("[SPA] Launching browser")
        await self.initialize()
        
        context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            }
        )
        
        page = await context.new_page()
        
        try:
            # Step 1: Navigate and wait for domcontentloaded
            logger.info(f"Navigating to: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            
            # Step 2: Hydration Verification
            logger.info("[SPA] Waiting hydration")
            if progress_callback:
                await progress_callback("[SPA] Waiting hydration")
            await self._wait_for_hydration(page)
            
            # Step 3: Wait for network activity to quiet down
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                logger.debug("Network idle state quiet wait timed out, continuing...")
 
            # Step 4: Auto-scroll progressive pass
            logger.info("[SPA] Starting scroll pass")
            if progress_callback:
                await progress_callback("[SPA] Starting scroll pass")
            await self._progressive_scroll(page)
            
            # Step 5: Wait for lazy-loaded dynamic content
            logger.info("[SPA] Waiting lazy content")
            if progress_callback:
                await progress_callback("[SPA] Triggering lazy content")
            await asyncio.sleep(2.0)
            
            # Step 6: Wait for DOM stabilization (text length + mutations decay)
            logger.info("[SPA] DOM stabilized")
            if progress_callback:
                await progress_callback("[SPA] Waiting stabilization")
            await self._stabilize_dom(page)
 
            # Step 7: Clean visible rendered DOM extraction
            logger.info("[SPA] Extracting rendered text")
            if progress_callback:
                await progress_callback("[SPA] Extracting rendered DOM")
            clean_html = await self._extract_visible_html(page)
            
            logger.info("[SPA] Generating llms output preparation complete")
            return clean_html

        except Exception as e:
            logger.error(f"Error during SPA rendering flow for {url}: {e}", exc_info=True)
            raise
        finally:
            await page.close()
            await context.close()

    async def _wait_for_hydration(self, page) -> bool:
        """
        Monitors root container occupancy and signals when client-side 
        frameworks have injected components.
        """
        hydration_check_script = """
        () => {
            const rootSelectors = ['#root', '#app', 'app-root', '#__next', '#_nuxt', '.app-container', 'body'];
            for (const selector of rootSelectors) {
                const el = document.querySelector(selector);
                if (el) {
                    // Check if elements are loaded inside root containers
                    const childrenCount = el.children.length;
                    const textLen = el.innerText ? el.innerText.trim().length : 0;
                    // If we have children or text, it indicates framework started hydration
                    if (childrenCount > 0 || textLen > 100) {
                        return true;
                    }
                }
            }
            return false;
        }
        """
        for attempt in range(20): # Max 10 seconds check
            try:
                hydrated = await page.evaluate(hydration_check_script)
                if hydrated:
                    logger.debug("Hydration check passed: elements detected inside root containers.")
                    return True
            except Exception as e:
                logger.debug(f"Hydration evaluation warning: {e}")
            await asyncio.sleep(0.5)
        return False

    async def _progressive_scroll(self, page):
        """
        Progressively scrolls the viewport to trigger IntersectionObservers 
        and lazy-loaded image segments.
        """
        progressive_scroll_script = """
        async () => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 300; // Small increment scroll steps
                const scrollHeight = document.body.scrollHeight;
                const maxScroll = Math.min(scrollHeight, 12000); // Bounded height limit to prevent hanging on infinite layouts

                const timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    totalHeight += distance;

                    if (totalHeight >= maxScroll) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 150); // Pause briefly between scrolls to allow rendering threads to process
            });
        }
        """
        try:
            await page.evaluate(progressive_scroll_script)
            # Short wait at the bottom
            await asyncio.sleep(1.0)
            # Progressive scroll back up to trigger any upper lazy modules
            await page.evaluate("window.scrollTo({top: 0, behavior: 'auto'})")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Progressive scroll pass hit a minor warning: {e}")

    async def _stabilize_dom(self, page, max_wait_sec: int = 15):
        """
        Ensures page has fully stabilized by evaluating the length of visible 
        innerText over consecutive periods, coupled with mutation silence checks.
        """
        previous_len = -1
        stable_count = 0
        interval = 0.5 # check every 500ms
        max_loops = int(max_wait_sec / interval)

        # Mutation check script runs in the browser context
        setup_mutation_script = """
        () => {
            window.__dom_mutations = 0;
            const observer = new MutationObserver(() => {
                window.__dom_mutations++;
            });
            observer.observe(document.body, { attributes: true, childList: true, subtree: true });
            window.__dom_observer = observer;
        }
        """
        try:
            await page.evaluate(setup_mutation_script)
        except Exception:
            pass

        for _ in range(max_loops):
            try:
                # 1. Fetch text length
                current_len = await page.evaluate("document.body.innerText ? document.body.innerText.length : 0")
                # 2. Fetch mutation numbers
                mutations = await page.evaluate("window.__dom_mutations || 0")
                # Reset browser mutations counter
                await page.evaluate("window.__dom_mutations = 0")

                logger.debug(f"Stabilization monitor: text_length={current_len}, mutations_count={mutations}")
                
                # Heuristic: If visible text length hasn't changed AND mutations are near zero, we are stabilized
                if current_len == previous_len and mutations < 5:
                    stable_count += 1
                else:
                    stable_count = 0
                
                # Requires consecutive stable passes (1.5 seconds of total silence)
                if stable_count >= 3:
                    logger.debug("DOM stabilization metrics met.")
                    break
                    
                previous_len = current_len
            except Exception as e:
                logger.warning(f"Error checking DOM stabilization loop: {e}")
                
            await asyncio.sleep(interval)

        # Clean up browser-side observer
        try:
            await page.evaluate("if(window.__dom_observer) { window.__dom_observer.disconnect(); }")
        except Exception:
            pass

    async def _extract_visible_html(self, page) -> str:
        """
        Harvests raw, rendered visible content elements directly from the Playwright 
        context, suppressing hidden blocks, scripts, framework hydration templates, 
        and metadata tags before BeautifulSoup parsing.
        """
        extraction_script = """
        () => {
            // Helper to determine if element is visible in the viewport context
            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    return false;
                }
                const rect = el.getBoundingClientRect();
                // If it's a completely flat layout tag (0px height/width), skip it
                if (rect.width === 0 && rect.height === 0) {
                    return false;
                }
                return true;
            };

            // Deep clone body to avoid destructive actions on original DOM
            const bodyClone = document.body.cloneNode(true);
            
            // Remove scripts, stylesheets, styles, forms, inputs, templates
            const stripSelectors = [
                'script', 'style', 'noscript', 'iframe', 'svg', 'form', 
                'input', 'button', 'select', 'textarea', 'dialog', 
                'template', '[hidden]', '[aria-hidden="true"]'
            ];
            
            stripSelectors.forEach(sel => {
                bodyClone.querySelectorAll(sel).forEach(el => el.remove());
            });

            // Strip out elements that are completely invisible
            // We run this by evaluating style attributes of the cloned DOM
            const allElements = bodyClone.getElementsByTagName('*');
            for (let i = allElements.length - 1; i >= 0; i--) {
                const el = allElements[i];
                // Check style directly in clone or computed styles if attached
                const style = el.getAttribute('style') || '';
                if (style.includes('display: none') || style.includes('visibility: hidden') || el.getAttribute('hidden') !== null) {
                    el.remove();
                }
            }
            // Append a custom title element so BeautifulSoup can extract descriptive page titles
            const titleEl = document.createElement("title");
            titleEl.innerText = document.title;
            bodyClone.appendChild(titleEl);

            return bodyClone.innerHTML;
        }
        """
        try:
            return await page.evaluate(extraction_script)
        except Exception as e:
            logger.error(f"Visible HTML harvesting script failed: {e}. Falling back to standard body content.")
            return await page.content()

    async def shutdown(self):
        """Cleanly releases browser lifetime context."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
