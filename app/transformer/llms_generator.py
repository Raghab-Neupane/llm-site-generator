def generate_llms_txt(site_name, pages):

    content = f"# {site_name}\n\n"

    content += (
        "> AI generated website knowledge base\n\n"
    )

    content += "## Important Pages\n\n"

    for page in pages:

        title = page["title"]

        url = page["url"]

        content += (
            f"- [{title}]({url})\n"
        )

    content += "\n"

    for page in pages:

        title = page["title"]

        markdown = page["markdown"]

        content += f"## {title}\n\n"

        content += markdown[:1000]

        content += "\n\n"

    return content