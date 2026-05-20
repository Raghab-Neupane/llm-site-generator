from fastapi import APIRouter
from fastapi.responses import FileResponse

from pydantic import BaseModel

from app.crawler.robots_parser import (
    parse_robots
)

from app.crawler.sitemap_parser import (
    parse_sitemap
)

from app.extractor.html_fetcher import (
    fetch_html
)

from app.transformer.markdown_generator import (
    generate_markdown
)

from app.transformer.llms_generator import (
    generate_llms_txt
)

from app.storage.file_writer import (
    save_llms_txt
)

router = APIRouter()


class CrawlRequest(BaseModel):
    url: str


@router.post("/crawl-site")
async def crawl_site(request: CrawlRequest):

    # STEP 1
    # PARSE ROBOTS.TXT

    robots_data = await parse_robots(
        request.url
    )

    sitemap_urls = robots_data[
        "sitemap_urls"
    ]

    if not sitemap_urls:

        return {
            "status": "error",
            "message": "No sitemap found"
        }

    # STEP 2
    # PARSE MAIN SITEMAP

    sitemap_data = await parse_sitemap(
        sitemap_urls[0]
    )

    actual_pages = sitemap_data[
        "actual_pages"
    ]

    # HANDLE NESTED SITEMAPS

    if not actual_pages:

        nested_sitemaps = sitemap_data.get(
            "sitemaps",
            []
        )

        for nested_sitemap in nested_sitemaps[:3]:

            nested_data = await parse_sitemap(
                nested_sitemap
            )

            nested_pages = nested_data.get(
                "actual_pages",
                []
            )

            actual_pages.extend(
                nested_pages
            )

    # STILL NO PAGES

    if not actual_pages:

        return {
            "status": "error",
            "message": "No actual pages found"
        }

    # STEP 3
    # FETCH PAGES

    pages_data = []

    for page_url in actual_pages[:3]:

        try:

            html = await fetch_html(
                page_url
            )

            markdown = generate_markdown(
                html,
                page_url
            )

            title = (
                markdown
                .split("\n")[0]
                .replace("#", "")
                .strip()
            )

            if not title:
                title = "No Title"

            pages_data.append({
                "title": title,
                "url": page_url,
                "markdown": markdown
            })

        except Exception as e:

            print(
                f"Error processing {page_url}: {e}"
            )

    # STEP 4
    # GENERATE SITE NAME

    site_name = (
        request.url
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
        .split("/")[0]
        .split(".")[0]
        .capitalize()
    )

    # STEP 5
    # GENERATE LLMS.TXT

    llms_txt = generate_llms_txt(
        site_name,
        pages_data
    )

    # STEP 6
    # SAVE FILE

    save_llms_txt(llms_txt)

    # STEP 7
    # RETURN RESPONSE

    return {
        "status": "success",
        "robots": robots_data,
        "sitemap": sitemap_data,
        "total_pages_processed": len(
            pages_data
        ),
        "llms_txt_preview": llms_txt[:5000]
    }


@router.get("/llms.txt")
async def get_llms_txt():

    return FileResponse(
        path="outputs/llms.txt",
        media_type="text/plain",
        filename="llms.txt"
    )