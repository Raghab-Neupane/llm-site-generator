import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, NavigableString

def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()

def extract_title(soup, url: str) -> str:
    # 1. Search for first h1
    h1 = soup.find("h1")
    if h1:
        text = clean_text(h1.get_text())
        if text and len(text) > 2:
            return text

    # 2. Fallback to HTML title
    if soup.title and soup.title.string:
        title_str = clean_text(soup.title.string)
        if title_str and len(title_str) > 2:
            return title_str

    # 3. Fallback to URL slug
    try:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path:
            last_segment = path.split("/")[-1]
            slug = last_segment.replace("-", " ").replace("_", " ")
            if slug:
                return slug.title()
    except Exception:
        pass

    return "Untitled Page"

def get_main_container(soup):
    for selector in ["main", "article", '[role="main"]', "section"]:
        el = soup.find(selector)
        if el:
            return el
            
    # Try to find the div with the most text density
    best_div = None
    max_text_len = 0
    for div in soup.find_all("div"):
        txt = div.get_text(strip=True)
        txt_len = len(txt)
        if txt_len > max_text_len:
            # Check link density (navigation menus have high link density)
            links_len = sum(len(a.get_text(strip=True)) for a in div.find_all("a"))
            # If less than 40% of the text is links, it's likely main content
            if txt_len > 0 and (links_len / txt_len) < 0.4:
                max_text_len = txt_len
                best_div = div
                
    if best_div:
        return best_div
        
    if soup.body:
        return soup.body
        
    return soup

def process_node(node, base_url: str, seen_content: set) -> str:
    if isinstance(node, NavigableString):
        return clean_text(str(node))

    if not node.name:
        return ""

    name = node.name.lower()
    
    # Elements to completely skip
    if name in [
        "script", "style", "nav", "footer", "header", "aside", 
        "noscript", "svg", "iframe", "form", "button", "link", 
        "select", "textarea", "input", "canvas"
    ]:
        return ""

    # Block-level deduplication
    if name in ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]:
        text = node.get_text(strip=True)
        if not text:
            return ""
        norm_text = re.sub(r'\W+', '', text).lower()
        # If it's a short generic string, don't deduplicate it (like bullet points/numbers)
        if len(norm_text) > 10:
            if norm_text in seen_content:
                return ""
            seen_content.add(norm_text)

    # Convert elements to Markdown
    if name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        level = int(name[1])
        prefix = "#" * level
        text = clean_text(node.get_text())
        if len(text) >= 2:
            return f"\n\n{prefix} {text}\n\n"
        return ""

    elif name == "p":
        text = clean_text(node.get_text())
        if len(text) >= 5:
            return f"\n\n{text}\n\n"
        return ""

    elif name == "blockquote":
        text = clean_text(node.get_text())
        if text:
            return f"\n\n> {text}\n\n"
        return ""

    elif name in ["ul", "ol"]:
        items = []
        is_ol = (name == "ol")
        idx = 1
        for child in node.find_all("li", recursive=False):
            li_text = clean_text(child.get_text())
            if li_text:
                prefix = f"{idx}. " if is_ol else "* "
                items.append(f"{prefix}{li_text}")
                idx += 1
        if items:
            return "\n" + "\n".join(items) + "\n"
        return ""

    elif name == "pre":
        code_tag = node.find("code")
        code_text = code_tag.get_text() if code_tag else node.get_text()
        if code_text.strip():
            return f"\n\n```\n{code_text.strip()}\n```\n\n"
        return ""

    elif name == "code":
        return f" `{node.get_text().strip()}` "

    elif name in ["strong", "b"]:
        text = node.get_text().strip()
        if text:
            return f" **{text}** "
        return ""

    elif name in ["em", "i"]:
        text = node.get_text().strip()
        if text:
            return f" *{text}* "
        return ""

    elif name == "a":
        href = node.get("href")
        text = clean_text(node.get_text())
        if not text or not href:
            return text or ""
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return text
        full_url = urljoin(base_url, href)
        return f" [{text}]({full_url}) "

    elif name == "table":
        rows = []
        for tr in node.find_all("tr"):
            cells = [clean_text(td.get_text()) for td in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(cells)
        if not rows:
            return ""
        try:
            col_widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
            md_table = []
            md_table.append("| " + " | ".join(str(rows[0][i]).ljust(col_widths[i]) for i in range(len(rows[0]))) + " |")
            md_table.append("| " + " | ".join("-" * col_widths[i] for i in range(len(rows[0]))) + " |")
            for row in rows[1:]:
                row_cells = row + [""] * (len(rows[0]) - len(row))
                md_table.append("| " + " | ".join(str(row_cells[i]).ljust(col_widths[i]) for i in range(len(rows[0]))) + " |")
            return "\n\n" + "\n".join(md_table) + "\n\n"
        except Exception:
            return ""

    # Container elements: traverse children
    res = []
    for child in node.children:
        part = process_node(child, base_url, seen_content)
        if part:
            res.append(part)
    return "".join(res)

def clean_markdown(md: str) -> str:
    # Limit consecutive newlines to exactly 2
    md = re.sub(r'\n{3,}', '\n\n', md)
    # Strip trailing whitespace on each line
    lines = [line.rstrip() for line in md.splitlines()]
    return "\n".join(lines).strip()

def generate_markdown(html: str, url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Clean HTML first by decomposing useless components
    for tag in soup([
        "script", "style", "nav", "footer", "header", "aside", 
        "noscript", "svg", "iframe", "form", "button", "link", 
        "select", "textarea", "input", "canvas"
    ]):
        tag.decompose()

    # 2. Extract title before main container narrows it
    title = extract_title(soup, url)

    # 3. Extract main content container
    main_container = get_main_container(soup)

    # 4. Recursively build markdown
    seen_content = set()
    raw_md = process_node(main_container, url, seen_content)

    # 5. Clean up markdown spacing
    cleaned_md = clean_markdown(raw_md)

    # 6. Ensure the markdown starts with the extracted title
    final_md = f"# {title}\n\n{cleaned_md}"
    return final_md