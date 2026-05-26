import re
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger("crawler.detector")

def detect_page_type(html: str) -> str:
    """
    Evaluates whether a page is a Single Page Application (SPA) or Static 
    using a multi-signal weighted scoring classifier.
    
    Weights:
    - Framework markers: +3 points
    - Root container divs: +2 points
    - JS bundle density: +2 points
    - Low semantic layout: +2 points
    
    Classifies as "spa" if total score >= 5, else "static".
    """
    if not html:
        return "static"

    score = 0
    signals = []

    soup = BeautifulSoup(html, "html.parser")

    # 1. Framework Markers (+3)
    framework_indicators = [
        "__NEXT_DATA__", 
        "window.__NUXT__", 
        "window.__INITIAL_STATE__",
        "window.__APOLLO_STATE__",
        "__NEXT_LOADED_PAGES__",
        "__remixContext",
        "ng-app",
        "ng-controller",
        "ng-version",
        "data-reactroot"
    ]
    has_fw_indicator = False
    for indicator in framework_indicators:
        if indicator in html:
            has_fw_indicator = True
            signals.append(f"Framework pattern: {indicator}")
            break
            
    if not has_fw_indicator:
        meta_generators = soup.find_all("meta", attrs={"name": "generator"})
        for meta in meta_generators:
            content = meta.get("content", "").lower()
            if any(fw in content for fw in ["react", "next.js", "nuxt", "angular", "vue"]):
                has_fw_indicator = True
                signals.append(f"Framework generator meta: {content}")
                break

    if has_fw_indicator:
        score += 3

    # 2. Root Container Divs (+2)
    root_ids = ["root", "app", "__next", "_nuxt", "svelte-root"]
    has_root_div = False
    for rid in root_ids:
        if soup.find("div", id=rid):
            has_root_div = True
            signals.append(f"Root container div: id='{rid}'")
            break
            
    if has_root_div:
        score += 2

    # 3. Script / JS Bundle Density (+2)
    scripts = soup.find_all("script")
    script_count = len(scripts)
    js_src_patterns = [
        r"/_next/static/",
        r"/static/js/",
        r"/assets/index\.[a-f0-9]+\.js",
        r"chunk-vendors",
        r"nuxt",
        r"app\.[a-f0-9]+\.js"
    ]
    bundle_matches = 0
    for script in scripts:
        src = script.get("src", "")
        if src:
            if any(re.search(pat, src, re.IGNORECASE) for pat in js_src_patterns):
                bundle_matches += 1

    # High scripts vs HTML size density
    html_len = len(html)
    if bundle_matches >= 2 or (script_count >= 5 and html_len < 100000):
        score += 2
        signals.append(f"High JS density: {bundle_matches} bundles, {script_count} script tags")

    # 4. Low Semantic Layout (+2)
    # Check if page body consists of sparse semantic elements (low visible text length vs script tag dominance)
    body = soup.find("body")
    if body:
        text_content = body.get_text(strip=True)
        # If there are scripts but visible text is extremely tiny, DOM structure is likely shell-only
        if len(text_content) < 800 and script_count >= 3:
            score += 2
            signals.append(f"Low semantic content: visible body text length {len(text_content)} chars")

    # Output log mapping the calculated confidence metrics
    logger.info(f"[DETECTOR] SPA confidence score: {score} (Signals: {', '.join(signals)})")

    if score >= 5:
        return "spa"
    return "static"
