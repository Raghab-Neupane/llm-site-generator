import re

def clean_markdown_content(markdown: str) -> str:
    """
    Cleans and normalizes page markdown content before inclusion in llms.txt.
    
    1. Why inline links collapse:
       During HTML parsing and conversion to markdown, adjacent hyperlink anchor tags within a single block
       (such as navigation menus, footer lists, or inline tags) are converted into inline markdown links
       next to each other: `[link1](url1) [link2](url2)`. When rendered in standard markdown viewers
       (e.g., GitHub, VSCode, or README previews), consecutive inline links on the same line collapse
       together and flow as a single messy text block.
       
    2. Why regex normalization fixes the issue:
       The regex `r'(\)\]?)\s+(\[)'` identifies the boundary between a closing link parenthesis `)` and the
       opening bracket `[` of an adjacent link separated by space. By replacing this boundary with double
       newlines (`\n\n`), we split the collapsed links onto their own separate paragraphs/lines.
       
    3. Where in the scraping pipeline this cleanup should occur:
       This cleanup must be executed in `llms_generator.py` right before the page's markdown content is truncated
       and concatenated into the final compiled `llms.txt` document. This keeps the core scraping logic decoupled
       from output presentation concerns.
    """
    if not markdown:
        return ""
        
    # Split adjacent inline markdown links onto separate lines
    # Detects: ) [ or )  [ and splits with double newlines
    markdown = re.sub(r'(\)\]?)\s+(\[)', r'\1\n\n\2', markdown)
    
    # Process lines: remove excessive spaces but preserve headers and lists
    cleaned_lines = []
    for line in markdown.splitlines():
        stripped_line = line.strip()
        
        # Preserve empty lines
        if not stripped_line:
            cleaned_lines.append("")
            continue
            
        # Preserve list item indentation if present (e.g. nested lists)
        if line.startswith("  ") or line.startswith("\t"):
            leading_space = line[:len(line) - len(line.lstrip())]
            cleaned_line = leading_space + stripped_line
        else:
            cleaned_line = stripped_line
            
        cleaned_lines.append(cleaned_line)
        
    markdown = "\n".join(cleaned_lines)
    
    # Collapse 3+ newlines into exactly 2 newlines (at most one blank line between paragraphs)
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    
    return markdown

def generate_llms_txt(site_name, pages):
    content = f"# {site_name}\n\n"
    content += "> AI generated website knowledge base\n\n"
    content += "## Important Pages\n\n"

    # IMPORTANT PAGES LIST
    for page in pages:
        title = page["title"]
        url = page["url"]
        content += f"* [{title}]({url})  \n"

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
        
        # Normalize formatting and split collapsed links
        cleaned_markdown = clean_markdown_content(cleaned_markdown)
        
        # Apply cleanup before content truncation (limit page details to 1000 characters)
        truncated_markdown = cleaned_markdown[:1000]

        section = f"## {title}\n\n"
        section += f"**Source:**\n{url}\n\n"
        section += f"**Description:**\n{description}\n\n"
        section += f"### Content\n\n{truncated_markdown}"
        page_sections.append(section)

    content += "\n\n---\n\n".join(page_sections)
    return content