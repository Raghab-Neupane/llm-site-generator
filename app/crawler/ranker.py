import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger("crawler.ranker")

class URLRanker:
    """
    A decoupled, highly specialized URL ranking, filtering, and 
    canonical normalization manager.
    """
    def __init__(self):
        pass

    def normalize_url(self, url: str) -> str:
        """Standardizes URLs by ignoring fragments and stripping marketing/tracking query parameters."""
        if not url:
            return ""
        url = url.strip()
        parsed = urlparse(url)
        
        # Lowercase scheme and hostname
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path
        
        # Remove trailing slash in path if not root
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
            
        # Clean tracking query parameters
        query_params = []
        if parsed.query:
            for pair in parsed.query.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                else:
                    k, v = pair, ""
                # Strip typical analytics params
                if k.lower() not in ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"]:
                    query_params.append(f"{k}={v}" if v else k)
        
        query = "&".join(query_params)
        normalized = f"{scheme}://{netloc}{path}"
        if query:
            normalized += f"?{query}"
            
        return normalized

    def is_valid_url(self, url: str, base_host: str) -> bool:
        """Applies filters to restrict links to the internal domain and drop garbage paths."""
        if not url:
            return False
            
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc.lower() != base_host:
            return False  # Only crawl internal links
            
        url_lower = url.lower()
        if "mailto:" in url_lower or "javascript:" in url_lower or "tel:" in url_lower:
            return False

        # Drop common spam/non-meaningful pages
        blacklisted_patterns = [
            "/login", "/signup", "/signin", "/register", "/auth", "/logout",
            "/cart", "/checkout", "/account", "/wp-admin", "/wp-content",
            "/wp-includes", "/admin", "/password-reset", "/forgot-password",
            "/dashboard"
        ]
        if any(pattern in url_lower for pattern in blacklisted_patterns):
            return False

        # Drop large downloads or assets directly
        blacklisted_extensions = (
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
            ".css", ".js", ".json", ".xml", ".mp4", ".mp3", ".avi", ".mov",
            ".woff", ".woff2", ".ttf", ".eot"
        )
        if url_lower.endswith(blacklisted_extensions):
            return False

        return True

    def calculate_priority(self, url: str) -> int:
        """
        Applies a semantic score to rank high-quality resource paths over marketing boilerplate.
        """
        url_lower = url.lower()
        score = 50  # Base level score

        # Prioritize developer-focused documentation segments
        high_priority_matches = {
            "/docs": 40,
            "/api": 35,
            "/guide": 30,
            "/developer": 30,
            "/tutorial": 25,
            "/reference": 20,
            "/blog": 15,
            "/kb": 15
        }
        
        for term, val in high_priority_matches.items():
            if term in url_lower:
                score += val

        # Deprioritize secondary corporate fluff or transaction structures
        low_priority_matches = {
            "/pricing": -20,
            "/contact": -15,
            "/about": -10,
            "/careers": -10,
            "/press": -10,
            "/legal": -15,
            "/privacy": -15,
            "/terms": -15
        }

        for term, val in low_priority_matches.items():
            if term in url_lower:
                score += val

        return score
