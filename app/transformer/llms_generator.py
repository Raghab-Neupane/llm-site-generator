import logging
import re

logger = logging.getLogger("crawler.transformer")

def clean_ui_junk(text: str) -> str:
    """Removes template dynamic expressions, call-to-actions, and UI repetitive banners."""
    # Remove dynamic template double brackets {{ ... }}
    text = re.sub(r'\{\{.*?\}\}', '', text)
    
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            cleaned_lines.append("")
            continue
            
        lower_line = line_stripped.lower()
        
        # Skip common call-to-action buttons or repetitive navigation links
        if any(term == lower_line for term in [
            "view more", "learn more", "read more", "click here", "sign up", "login", 
            "sign-up", "log-in", "register", "submit", "apply now", "download now", 
            "get started", "privacy policy", "terms of service", "cookie settings",
            "all rights reserved", "copyright", "view menu", "payment menu"
        ]):
            continue
            
        # Skip dynamic script wrappers or raw bracket residue
        if line_stripped in ["{", "}", "[", "]", "};", "];"]:
            continue
            
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines)

def generate_semantic_description(page_title: str, raw_markdown: str, meta_desc: str) -> str:
    """Generates a truthful, non-hallucinated description based on meta-desc, headings, and text content."""
    if meta_desc and len(meta_desc.strip()) > 20:
        return meta_desc.strip()
        
    # Clean the markdown text to get plain words
    clean_text = re.sub(r'[\#\*\_\[\]\(\)\-\`\|\:\!]', ' ', raw_markdown)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    # Extract first few sentences or headings
    sentences = [s.strip() for s in re.split(r'[\.\!\?]', clean_text) if s.strip()]
    if sentences:
        summary_candidate = ". ".join(sentences[:2]) + "."
        if len(summary_candidate) > 40:
            return summary_candidate
            
    # Fallback using headings
    headings = [line.strip("# ") for line in raw_markdown.split("\n") if line.strip().startswith("##")]
    if headings:
        return f"Explore resources, tutorials, and information on: {', '.join(headings[:3])}."
        
    return f"A detailed resource and guide covering various aspects of {page_title}."

def transform_markdown_to_semantic_hierarchy(page_title: str, raw_markdown: str, assets: dict) -> str:
    """Parses raw content, associates media assets, cleans UI junk, and formats into professional semantic categories and cards."""
    # 1. Clean the raw text
    clean_md = clean_ui_junk(raw_markdown)
    
    lines = clean_md.split("\n")
    current_category = "Overview"
    categories = {}  # category_name -> list of cards
    
    images_list = assets.get("images", [])
    available_images = list(images_list)
    used_images = set()

    # Helper to find a matching image for a given text block
    def find_matching_image(text):
        if not text:
            return None
        text_lower = text.lower()
        for img in available_images:
            if img["url"] in used_images:
                continue
            alt = img.get("alt", "").lower()
            url_path = img["url"].lower()
            # Alt text correlation or url match
            if (alt and alt != "image description not provided" and alt in text_lower) or any(term in url_path for term in text_lower.split() if len(term) > 3):
                used_images.add(img["url"])
                return img
        # Fallback to first unused image
        for img in available_images:
            if img["url"] not in used_images:
                used_images.add(img["url"])
                return img
        return None

    # Helper to commit a structured card
    def commit_card(category, title, content_lines):
        if not title and not content_lines:
            return
        if category not in categories:
            categories[category] = []
            
        clean_title = (title or page_title or "Overview").strip()
        card_name = clean_title.split("&")[0].split("/")[0].split("-")[0].strip()
        if len(card_name) > 30:
            card_name = card_name[:27] + "..."
            
        content_text = " ".join([l.strip() for l in content_lines if l.strip()])
        if not content_text:
            content_text = f"Discover information regarding {clean_title}."
            
        # Find matching image
        matched_img = find_matching_image(clean_title + " " + content_text)
        img_markdown = ""
        if matched_img:
            img_markdown = f"![{matched_img.get('alt', 'Image')}]({matched_img['url']})"
            
        categories[category].append({
            "card_name": card_name,
            "image_md": img_markdown,
            "semantic_title": clean_title,
            "content": content_text
        })

    buffer_lines = []
    current_card_title = None

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
            
        # Detect category headings
        if line_stripped.startswith(("#", "##", "###", "####")):
            if current_card_title or buffer_lines:
                commit_card(current_category, current_card_title, buffer_lines)
                buffer_lines = []
                current_card_title = None
                
            heading_text = re.sub(r'^#+\s+', '', line_stripped).strip()
            if heading_text:
                current_category = heading_text
            continue
            
        # Detect potential cards in lists
        list_match = re.match(r'^[\-\*\+]\s+(.*)$', line_stripped)
        if list_match:
            item_text = list_match.group(1).strip()
            bold_match = re.match(r'^\*\*(.*?)\*\*(.*)$', item_text)
            if bold_match:
                if current_card_title or buffer_lines:
                    commit_card(current_category, current_card_title, buffer_lines)
                    buffer_lines = []
                current_card_title = bold_match.group(1).strip()
                desc_text = bold_match.group(2).strip(" :-")
                buffer_lines = [desc_text] if desc_text else []
            else:
                if current_card_title or buffer_lines:
                    commit_card(current_category, current_card_title, buffer_lines)
                    buffer_lines = []
                words = item_text.split()
                if len(words) > 3:
                    current_card_title = " ".join(words[:3])
                    buffer_lines = [item_text]
                else:
                    current_card_title = item_text
                    buffer_lines = [item_text]
            continue
            
        # Detect bold heading-like paragraph
        bold_para_match = re.match(r'^\*\*(.*?)\*\*$', line_stripped)
        if bold_para_match:
            if current_card_title or buffer_lines:
                commit_card(current_category, current_card_title, buffer_lines)
                buffer_lines = []
            current_card_title = bold_para_match.group(1).strip()
            continue
            
        buffer_lines.append(line_stripped)

    # Commit final card
    if current_card_title or buffer_lines:
        commit_card(current_category, current_card_title, buffer_lines)

    # Clean up empty categories or default blocks
    if not categories:
        categories["Overview"] = [{
            "card_name": page_title,
            "image_md": "",
            "semantic_title": page_title,
            "content": "Discover documentation resources and content details."
        }]

    # --- 11. Preserving Asset Relationships ---
    
    # 11b. Group Videos under a category card group
    videos_list = assets.get("videos", [])
    if videos_list:
        v_category = "Multimedia & Videos"
        categories[v_category] = []
        for v in videos_list:
            v_title = v.get("title", "Video Embed")
            v_card_name = v_title[:27] + "..." if len(v_title) > 30 else v_title
            categories[v_category].append({
                "card_name": v_card_name,
                "image_md": "", # Videos do not render inline images usually
                "semantic_title": v_title,
                "content": f"[Watch Video Resource]({v['url']})"
            })

    # 11c. Group Technical Files under a category card group (file-to-heading relation)
    files_list = assets.get("files", [])
    if files_list:
        f_category = "Technical Resources & Downloads"
        categories[f_category] = []
        for f in files_list:
            f_name = f.get("filename", "Download Link")
            f_card_name = f_name[:27] + "..." if len(f_name) > 30 else f_name
            categories[f_category].append({
                "card_name": f_card_name,
                "image_md": "",
                "semantic_title": f.get("context_heading", "Developer Asset"),
                "content": f"[{f_name}]({f['url']})"
            })

    # Group External Reference Links
    links_list = assets.get("links", [])
    external_links = [l for l in links_list if not l.get("is_internal")]
    if external_links:
        l_category = "External References"
        categories[l_category] = []
        for l in external_links[:15]: # Limit to top 15 external links
            anchor = l.get("anchor_text", "Reference Link")
            l_card_name = anchor[:27] + "..." if len(anchor) > 30 else anchor
            categories[l_category].append({
                "card_name": l_card_name,
                "image_md": "",
                "semantic_title": f"Reference: {anchor}",
                "content": f"[{anchor}]({l['url']})"
            })

    # Render category sections and cards in the canonical structure
    formatted_lines = []
    for cat_name, cards in categories.items():
        if not cards:
            continue
            
        formatted_lines.append(f"#### {cat_name}")
        formatted_lines.append("")
        
        for card in cards:
            formatted_lines.append(card["card_name"])
            formatted_lines.append("")
            
            if card["image_md"]:
                formatted_lines.append(card["image_md"])
                formatted_lines.append("")
                
            formatted_lines.append(f"##### {card['semantic_title']}")
            formatted_lines.append("")
            
            if card["content"] and card["content"].lower() != card["semantic_title"].lower():
                formatted_lines.append(card["content"])
                formatted_lines.append("")
                
    return "\n".join(formatted_lines).strip()

def generate_llms_txt(site_name: str, pages_data: list, base_url: str) -> str:
    """
    Transforms the crawled semantic page models and assets into a high-quality, 
    compact, standard-compliant `llms.txt` and unified markdown file matching 
    the canonical professional semantic crawler template.
    """
    logger.info("[TRANSFORMER] Generating llms.txt")
    lines = []
    
    # 1. Header & Title Block
    lines.append(f"# {site_name}")
    lines.append("")
    lines.append("> AI generated website knowledge base")
    lines.append("")
    
    # 2. Section: Important Pages
    lines.append("## Important Pages")
    lines.append("")
    for p in pages_data:
        lines.append(f"* [{p['title']}]({p['url']})")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 3. Section: Content Sections
    for i, p in enumerate(pages_data):
        lines.append(f"## {p['title']}")
        lines.append("")
        
        lines.append("**Source:**")
        lines.append(p["url"])
        lines.append("")
        
        semantic_desc = generate_semantic_description(p["title"], p["markdown"], p.get("description", ""))
        lines.append("**Description:**")
        lines.append(semantic_desc)
        lines.append("")
        
        lines.append("### Content")
        lines.append("")
        
        # 4. Generate Category and Semantic Card layout
        hierarchy_md = transform_markdown_to_semantic_hierarchy(p["title"], p["markdown"], p.get("assets", {}))
        lines.append(hierarchy_md)
        lines.append("")
        
        if i < len(pages_data) - 1:
            lines.append("---")
            lines.append("")
            
    return "\n".join(lines).strip()
