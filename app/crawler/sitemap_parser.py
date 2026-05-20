import httpx
import xml.etree.ElementTree as ET


async def parse_sitemap(sitemap_url: str):

    try:

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0
        ) as client:

            response = await client.get(
                sitemap_url
            )

            xml_text = response.text

    except Exception as e:

        return {
            "sitemap_url": sitemap_url,
            "actual_pages": [],
            "error": str(e)
        }

    actual_pages = []
    sitemaps = []

    try:

        root = ET.fromstring(xml_text)

        namespace = ""

        if "}" in root.tag:
            namespace = root.tag.split("}")[0] + "}"

        # HANDLE <urlset>

        if "urlset" in root.tag:

            for url in root.findall(
                f".//{namespace}url"
            ):

                loc = url.find(
                    f"{namespace}loc"
                )

                if loc is not None:

                    actual_pages.append(
                        loc.text
                    )

        # HANDLE <sitemapindex>

        elif "sitemapindex" in root.tag:

            for sitemap in root.findall(
                f".//{namespace}sitemap"
            ):

                loc = sitemap.find(
                    f"{namespace}loc"
                )

                if loc is not None:

                    sitemaps.append(
                        loc.text
                    )

    except Exception as e:

        return {
            "sitemap_url": sitemap_url,
            "actual_pages": [],
            "error": str(e),
            "raw_preview": xml_text[:500]
        }

    return {
        "sitemap_url": sitemap_url,
        "total_sitemaps": len(
            sitemaps
        ),
        "sitemaps": sitemaps,
        "actual_pages": actual_pages[:10]
    }