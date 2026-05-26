import re
import logging
from bs4 import BeautifulSoup, Comment

logger = logging.getLogger("spa.cleaner")

class SPACleaner:
    """
    Scrubs dynamically rendered HTML DOM strings to strip out 
    client-side framework artifacts, hydration directives, and inline state dumps.
    """
    def __init__(self):
        pass

    def clean_html(self, html: str) -> str:
        """
        Processes and purges framework tags, custom comment descriptors, 
        and script variables from dynamic layouts.
        """
        if not html:
            return ""

        soup = BeautifulSoup(html, "html.parser")

        # 1. Purge all HTML comments (Angular/Vue virtual nodes are stored in comments)
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()

        # 2. Purge unwanted technical markup
        unwanted_tags = ["script", "style", "noscript", "template", "dialog"]
        for tag in soup.find_all(unwanted_tags):
            tag.extract()

        # 3. Clean Vue/Angular directives and attribute states recursively
        for tag in soup.find_all(True):
            attrs_to_remove = []
            for attr in tag.attrs:
                attr_lower = attr.lower()
                # Angular ngIf, ngRepeat, ng-reflect-*
                # Vue data-v-* directives, v-cloak
                if attr_lower.startswith(("ng-", "v-", "data-v-")) or attr_lower in [
                    "v-cloak", "ng-version", "ng-reflect-ng-if", 
                    "ng-reflect-ng-for", "ng-reflect-ng-repeat", "react-root"
                ]:
                    attrs_to_remove.append(attr)
            for attr in attrs_to_remove:
                del tag.attrs[attr]

        # Return clean visual DOM string
        return str(soup)
