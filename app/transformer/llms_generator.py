import re

def generate_llms_txt(site_name, pages):
    content = f"# {site_name}\n\n"
    content += "> AI generated website knowledge base\n\n"
    content += "## Important Pages\n\n"

    # IMPORTANT PAGES LIST
    for page in pages:
        title = page["title"]
        url = page["url"]
        content += f"* [{title}]({url})\n"

    content += "\n---\n\n"

    # PAGE CONTENT SECTIONS
    page_sections = []
    for page in pages:
        title = page["title"]
        url = page["url"]
        description = page["description"]
        markdown = page["markdown"]

        # Clean top-level heading duplication from markdown
        cleaned_markdown = markdown.strip()
        try:
            title_escaped = re.escape(title)
            cleaned_markdown = re.sub(rf"^#\s+{title_escaped}\s*\n+", "", cleaned_markdown, flags=re.IGNORECASE)
            cleaned_markdown = re.sub(r"^#\s+Untitled Page\s*\n+", "", cleaned_markdown, flags=re.IGNORECASE)
        except Exception:
            pass
        cleaned_markdown = cleaned_markdown.strip()

        section = f"## {title}\n\n"
        section += f"**Source:**\n{url}\n\n"
        section += f"**Description:**\n{description}\n\n"
        section += f"### Content\n\n{cleaned_markdown}"
        page_sections.append(section)

    content += "\n\n---\n\n".join(page_sections)
    return content