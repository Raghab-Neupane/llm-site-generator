from bs4 import BeautifulSoup


def generate_markdown(html: str, url: str):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    for tag in soup([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside"
    ]):
        tag.decompose()

    title = (
        soup.title.string.strip()
        if soup.title else "No Title"
    )

    markdown = f"# {title}\n\n"

    markdown += f"> Source: {url}\n\n"

    main = soup.find("main")

    content = main if main else soup

    headings = content.find_all(
        ["h1", "h2", "h3"]
    )

    for heading in headings[:10]:

        text = heading.get_text(
            strip=True
        )

        if len(text) < 3:
            continue

        level = heading.name

        if level == "h1":
            markdown += f"# {text}\n\n"

        elif level == "h2":
            markdown += f"## {text}\n\n"

        elif level == "h3":
            markdown += f"### {text}\n\n"

    paragraphs = content.find_all("p")

    for p in paragraphs[:15]:

        text = p.get_text(
            strip=True
        )

        if len(text) > 60:

            markdown += f"{text}\n\n"

    return markdown