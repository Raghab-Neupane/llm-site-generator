import re
import logging
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Comment, Tag

logger = logging.getLogger("crawler.extractor")

class PageExtractor:
    """
    A professional semantic content and asset extractor.
    Applies custom readability cleaning and extracts rich assets 
    (images, videos, files, and links) along with their semantic context.
    """
    def __init__(self, base_url: str):
        self.base_url = base_url

    def extract(self, html: str, current_url: str) -> dict:
        """
        Parses HTML page content and returns a structured dictionary containing
        cleaned text, markdown, metadata, and all extracted assets.
        """
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        
        # 1. Parse Metadata first
        title = self._extract_title(soup)
        meta_desc = self._extract_meta_description(soup)
        
        # 2. Extract Assets prior to aggressive DOM stripping
        images = self._extract_images(soup, current_url)
        videos = self._extract_videos(soup, current_url)
        files = self._extract_files(soup, current_url)
        links = self._extract_links(soup, current_url)

        # 3. Clean page layout boilerplate (nav, footer, sidebars, scripts, etc.)
        self._clean_boilerplate(soup)
        
        # 4. Generate clean readable markdown
        markdown = self._html_to_clean_markdown(soup, current_url)
        
        return {
            "title": title,
            "description": meta_desc,
            "url": current_url,
            "markdown": markdown,
            "assets": {
                "images": images,
                "videos": videos,
                "files": files,
                "links": links
            }
        }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extracts the cleanest, most descriptive page title."""
        # Try h1 first
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(strip=True)
            
        # Fall back to page title
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            # Clean common trailing site names e.g. "Docs | MySite" -> "Docs"
            t = title_tag.get_text(strip=True)
            t = re.split(r'\s+[\-|\|•]\s+', t)[0]
            return t
            
        return "Untitled Page"

    def _extract_meta_description(self, soup: BeautifulSoup) -> str:
        """Extracts the meta description content if present."""
        meta = soup.find("meta", attrs={"name": "description"}) or \
               soup.find("meta", attrs={"property": "og:description"})
        if meta and meta.get("content"):
            return meta.get("content").strip()
        return ""

    def _clean_boilerplate(self, soup: BeautifulSoup):
        """A readability-style layout cleaner that purges structural noise."""
        # Remove comments
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Structural HTML tags to remove
        unwanted_tags = [
            "script", "style", "noscript", "iframe", "svg", "form", "input", "button",
            "dialog", "select", "option", "textarea", "head", "link", "meta"
        ]
        for tag in soup.find_all(unwanted_tags):
            tag.extract()

        # Purge boilerplate components by CSS classes / IDs
        noisy_selectors = [
            # Headers & Navs
            "nav", "header", ".nav", ".navbar", ".navigation", ".menu", ".header", "#header", "#nav",
            # Footers
            "footer", ".footer", "#footer", ".subfooter",
            # Sidebars & Widgets
            "aside", ".sidebar", ".widget", ".aside", "#sidebar", ".right-bar", ".left-bar",
            # Overlays / Popups / Badges
            ".cookie", ".consent", ".banner", ".popup", ".modal", ".dialog", ".overlay", ".toast",
            # CTA & Marketing & Social share widgets
            ".cta", ".newsletter", ".subscribe", ".share", ".social", ".promo", ".ads", ".advertisement",
            # Breadcrumbs
            ".breadcrumb", ".breadcrumbs"
        ]
        
        for selector in noisy_selectors:
            try:
                for element in soup.select(selector):
                    element.extract()
            except Exception:
                pass

        # Strip framework binding attributes and markers (Angular, Vue, React placeholders)
        for tag in soup.find_all(True):
            attrs_to_remove = []
            for attr in tag.attrs:
                attr_lower = attr.lower()
                if attr_lower.startswith(("ng-", "v-", "data-v-")) or attr_lower in ["v-cloak", "ng-version", "ng-reflect-ng-if", "ng-reflect-ng-for", "ng-reflect-ng-repeat"]:
                    attrs_to_remove.append(attr)
            for attr in attrs_to_remove:
                del tag.attrs[attr]

    def _extract_images(self, soup: BeautifulSoup, current_url: str) -> list[dict]:
        """Extracts highly relevant, semantic image links with descriptions."""
        images = []
        seen_urls = set()
        
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if not src:
                continue
                
            full_url = urljoin(current_url, src)
            if full_url in seen_urls:
                continue
                
            alt = (img.get("alt") or "").strip()
            
            # Heuristic Filtering:
            # 1. Skip trackers & spacer pixels (often 1x1 base64 or small image tags)
            if "data:image" in src and "base64" in src and len(src) < 1000:
                continue
                
            # Parse size metrics if specified
            width = img.get("width")
            height = img.get("height")
            
            try:
                if width and int(width) <= 24: continue
                if height and int(height) <= 24: continue
            except ValueError:
                pass
                
            # Filter decorative icons by naming convention
            src_lower = src.lower()
            alt_lower = alt.lower()
            if any(term in src_lower or term in alt_lower for term in ["icon", "logo-small", "avatar", "spacer", "pixel", "tracker"]):
                # Retain structural brand logos if high-quality
                if "logo" in src_lower and ("nav" not in src_lower):
                    pass
                else:
                    continue

            # Classify semantic role
            role = "content_image"
            if "banner" in src_lower or "hero" in src_lower:
                role = "banner"
            elif "logo" in src_lower:
                role = "logo"

            seen_urls.add(full_url)
            images.append({
                "url": full_url,
                "alt": alt if alt else "Image description not provided",
                "role": role
            })
            
        return images

    def _extract_videos(self, soup: BeautifulSoup, current_url: str) -> list[dict]:
        """Extracts direct video assets and dynamic iframe media embeds (YouTube, Vimeo)."""
        videos = []
        seen_urls = set()

        # 1. HTML5 Video tags
        for vid in soup.find_all("video"):
            src = vid.get("src")
            if not src:
                source_tag = vid.find("source")
                if source_tag:
                    src = source_tag.get("src")
            if src:
                full_url = urljoin(current_url, src)
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    videos.append({
                        "url": full_url,
                        "title": vid.get("title") or "HTML5 Direct Video",
                        "type": "mp4",
                        "thumbnail": vid.get("poster")
                    })

        # 2. Embedded Video iframes (Parsed before stripped in cleaning step)
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src") or iframe.get("data-src")
            if not src:
                continue
                
            # Detect YouTube or Vimeo signatures
            video_platform = None
            if "youtube.com" in src or "youtu.be" in src:
                video_platform = "youtube"
            elif "vimeo.com" in src:
                video_platform = "vimeo"
                
            if video_platform:
                full_url = urljoin(current_url, src)
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    title = iframe.get("title") or f"{video_platform.capitalize()} Video Embed"
                    videos.append({
                        "url": full_url,
                        "title": title.strip(),
                        "type": video_platform,
                        "thumbnail": None
                    })

        return videos

    def _extract_files(self, soup: BeautifulSoup, current_url: str) -> list[dict]:
        """
        Extracts relevant developer assets (.pdf, .docx, .zip, etc.)
        along with nearby semantic heading context.
        """
        files = []
        seen_urls = set()
        file_extensions = (".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".tar", ".gz")
        
        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href:
                continue
                
            parsed = urlparse(href)
            path_lower = parsed.path.lower()
            
            if any(path_lower.endswith(ext) for ext in file_extensions):
                full_url = urljoin(current_url, href)
                if full_url in seen_urls:
                    continue
                    
                seen_urls.add(full_url)
                anchor_text = anchor.get_text(strip=True) or "Download File"
                
                # Fetch closest preceding heading context
                heading_context = "General Resource"
                parent = anchor.parent
                found = False
                depth = 0
                
                # Walk up DOM tree and inspect siblings to search for nearest preceding heading
                while parent and not found and depth < 6:
                    # Look at current level's previous siblings
                    sibling = parent
                    while sibling:
                        # Inspect siblings if they are Tag elements
                        if isinstance(sibling, Tag):
                            if sibling.name in ["h1", "h2", "h3", "h4", "h5"]:
                                heading_context = sibling.get_text(strip=True)
                                found = True
                                break
                            # If a sibling element contains a heading, grab it
                            heading_in_sibling = sibling.find(["h1", "h2", "h3", "h4", "h5"])
                            if heading_in_sibling:
                                heading_context = heading_in_sibling.get_text(strip=True)
                                found = True
                                break
                        sibling = sibling.previous_sibling
                    
                    if found:
                        break
                    parent = parent.parent
                    depth += 1
                
                files.append({
                    "url": full_url,
                    "filename": anchor_text,
                    "context_heading": heading_context
                })
                
        return files

    def _extract_links(self, soup: BeautifulSoup, current_url: str) -> list[dict]:
        """Extracts high quality internal navigation links and reference links."""
        links = []
        seen_urls = set()
        
        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href:
                continue
                
            # Skip fragments, js triggers, mailto
            href_clean = href.strip()
            if href_clean.startswith("#") or href_clean.lower().startswith(("javascript:", "mailto:", "tel:")):
                continue
                
            full_url = urljoin(current_url, href_clean)
            # Remove fragment for deduplication
            full_url_no_frag = full_url.split("#")[0].rstrip("/")
            
            if full_url_no_frag in seen_urls:
                continue
                
            anchor_text = anchor.get_text(strip=True)
            # Ignore empty anchor text link structures
            if not anchor_text or len(anchor_text) < 2:
                continue
                
            seen_urls.add(full_url_no_frag)
            
            # Determine internal vs external
            parsed_base = urlparse(self.base_url)
            parsed_link = urlparse(full_url)
            is_internal = (parsed_link.netloc == parsed_base.netloc) or (not parsed_link.netloc)
            
            links.append({
                "url": full_url,
                "anchor_text": anchor_text,
                "is_internal": is_internal
            })
            
        return links

    def _html_to_clean_markdown(self, element, current_url: str) -> str:
        """
        Custom highly optimized DOM-to-Markdown formatter.
        Translates semantic HTML structure into clean, compact, human-readable markdown.
        """
        markdown_lines = []
        
        def recurse(node):
            if node.name is None:
                # Text node
                text = node.string
                if text:
                    # Clean whitespaces
                    text = re.sub(r'[ \t\r\n\f]+', ' ', text)
                    if text != ' ':
                        markdown_lines.append(text)
                return

            if node.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                level = int(node.name[1])
                prefix = "#" * level
                markdown_lines.append(f"\n\n{prefix} {node.get_text(strip=True)}\n")
                
            elif node.name == "p":
                markdown_lines.append("\n\n")
                for child in node.children:
                    recurse(child)
                markdown_lines.append("\n")
                
            elif node.name in ["ul", "ol"]:
                markdown_lines.append("\n\n")
                for child in node.find_all("li", recursive=False):
                    markdown_lines.append("- ")
                    for grandchild in child.children:
                        recurse(grandchild)
                    markdown_lines.append("\n")
                markdown_lines.append("\n")
                
            elif node.name == "pre":
                code_tag = node.find("code")
                lang = ""
                if code_tag and code_tag.get("class"):
                    classes = code_tag.get("class")
                    for c in classes:
                        if c.startswith("language-"):
                            lang = c.replace("language-", "")
                code_text = node.get_text()
                markdown_lines.append(f"\n\n```{lang}\n{code_text.strip()}\n```\n\n")
                
            elif node.name == "code":
                markdown_lines.append(f" `{node.get_text(strip=True)}` ")
                
            elif node.name in ["strong", "b"]:
                markdown_lines.append(" **")
                for child in node.children:
                    recurse(child)
                markdown_lines.append("** ")
                
            elif node.name in ["em", "i"]:
                markdown_lines.append(" *")
                for child in node.children:
                    recurse(child)
                markdown_lines.append("* ")
                
            elif node.name == "blockquote":
                markdown_lines.append("\n\n> ")
                for child in node.children:
                    recurse(child)
                markdown_lines.append("\n\n")
                
            elif node.name == "a":
                href = node.get("href")
                text = node.get_text(strip=True)
                if href and text:
                    full_link = urljoin(current_url, href)
                    markdown_lines.append(f" [{text}]({full_link}) ")
                else:
                    for child in node.children:
                        recurse(child)
                        
            elif node.name in ["table", "thead", "tbody", "tr", "th", "td"]:
                # Simply extract the visible text to keep layouts readable without heavy table cluttering, 
                # but preserve clear structure.
                if node.name == "tr":
                    markdown_lines.append("\n| ")
                    for cell in node.find_all(["th", "td"], recursive=False):
                        cell_txt = cell.get_text(strip=True)
                        markdown_lines.append(f"{cell_txt} | ")
                else:
                    for child in node.children:
                        if child.name:
                            recurse(child)
            else:
                for child in node.children:
                    recurse(child)

        recurse(element)
        
        # Post-process whitespaces
        md_text = "".join(markdown_lines)
        md_text = re.sub(r'\n{3,}', '\n\n', md_text)
        md_text = re.sub(r' +', ' ', md_text)
        return md_text.strip()
