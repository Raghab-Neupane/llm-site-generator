import logging
from app.crawler.extractor import PageExtractor
from app.spa.cleaner import SPACleaner

logger = logging.getLogger("spa.extractor")

class SPAExtractor(PageExtractor):
    """
    Dynamic page extraction segment that wraps PageExtractor with custom 
    SPACleaner pre-filters to scrub framework junk.
    """
    def __init__(self, base_url: str):
        super().__init__(base_url)
        self.cleaner = SPACleaner()

    def extract(self, html: str, current_url: str) -> dict:
        """Cleans dynamic framework directives and runs robust semantic extraction."""
        logger.info(f"[EXTRACTOR] Cleaning content from {current_url}")
        
        # 1. Strip Angular/Vue template bindings and comment structures
        cleaned_html = self.cleaner.clean_html(html)
        
        # 2. Extract standard semantic assets, core content, and clean markdown
        return super().extract(cleaned_html, current_url)
