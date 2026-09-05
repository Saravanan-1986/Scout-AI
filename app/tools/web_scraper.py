import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def scrape_url(url: str, timeout: int = 10) -> str:
    """Scrapes raw text content from a target webpage URL with realistic browser headers."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Decompose unwanted elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "iframe"]):
            tag.decompose()

        # Target main content containers if available
        main_content = soup.find("main") or soup.find("article") or soup.body or soup

        text = main_content.get_text(separator=" ", strip=True)
        cleaned_text = " ".join(text.split())
        return cleaned_text[:8000]
    except Exception as e:
        logger.warning(f"Failed to scrape URL '{url}': {e}")
        return ""
