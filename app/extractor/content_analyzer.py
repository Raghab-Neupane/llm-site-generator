from bs4 import BeautifulSoup

def weak_content(html: str) -> bool:

    if not html:
        return True

    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text(strip=True)

    if len(text) < 500:
        return True

    if soup.find(id="app") and len(text) < 1000:
        return True

    if soup.find(id="root") and len(text) < 1000:
        return True

    headings = soup.find_all(["h1", "h2", "h3"])

    if len(headings) == 0:
        return True

    return False