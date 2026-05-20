import httpx


async def parse_robots(base_url: str):

    base_url = base_url.rstrip("/")

    robots_url = f"{base_url}/robots.txt"

    sitemap_urls = []

    try:

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0
        ) as client:

            response = await client.get(
                robots_url
            )

            robots_text = response.text

    except Exception as e:

        return {
            "robots_url": robots_url,
            "sitemap_urls": [],
            "raw_preview": "",
            "error": str(e)
        }

    lines = robots_text.splitlines()

    for line in lines:

        line = line.strip()

        if "sitemap:" in line.lower():

            try:

                sitemap_url = (
                    line
                    .split(":", 1)[1]
                    .strip()
                )

                sitemap_urls.append(
                    sitemap_url
                )

            except Exception:
                pass

    return {
        "robots_url": robots_url,
        "sitemap_urls": sitemap_urls,
        "raw_preview": robots_text[:500]
    }