from playwright.async_api import async_playwright


async def fetch_spa_html(url: str) -> str:

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        # WAIT FOR MAIN CONTENT
        try:
            await page.wait_for_selector(
                "h1",
                timeout=10000
            )
        except:
            pass

        # EXTRA HYDRATION STABILIZATION
        await page.wait_for_timeout(3000)

        # SCROLL TO TRIGGER LAZY LOADING
        await page.evaluate("""
            window.scrollTo(0, document.body.scrollHeight)
        """)

        await page.wait_for_timeout(2000)

        # EXTRACT ONLY VISIBLE RENDERED TEXT
        text = await page.locator("body").inner_text()

        await browser.close()

        return text