from bs4 import BeautifulSoup


def extract_metadata(html: str):

    soup = BeautifulSoup(html, "html.parser")

    title = (
        soup.title.string.strip()
        if soup.title else None
    )

    description_tag = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    description = (
        description_tag.get("content")
        if description_tag else "No Description"
    )

    canonical_tag = soup.find(
        "link",
        attrs={"rel": "canonical"}
    )

    canonical_url = (
        canonical_tag.get("href")
        if canonical_tag else None
    )

    og_title = soup.find(
        "meta",
        attrs={"property": "og:title"}
    )

    og_description = soup.find(
        "meta",
        attrs={"property": "og:description"}
    )

    headings = []

    for tag in soup.find_all(
        ["h1", "h2", "h3"]
    ):

        text = tag.get_text(strip=True)

        if text:
            headings.append({
                "tag": tag.name,
                "text": text
            })

    paragraphs = []

    for p in soup.find_all("p"):

        text = p.get_text(strip=True)

        if text:
            paragraphs.append(text)

    links = []

    for a in soup.find_all("a", href=True):

        links.append({
            "text": a.get_text(strip=True),
            "href": a["href"]
        })

    images = []

    for img in soup.find_all("img"):

        images.append({
            "src": img.get("src"),
            "alt": img.get("alt")
        })

    metadata = {
        "title": title,
        "description": description,
        "canonical_url": canonical_url,

        "og_title": (
            og_title.get("content")
            if og_title else None
        ),

        "og_description": (
            og_description.get("content")
            if og_description else None
        ),

        "headings": headings[:20],
        "paragraphs": paragraphs[:10],
        "links": links[:20],
        "images": images[:10]
    }

    return metadata