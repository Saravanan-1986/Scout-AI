"""Web page reader / scraper tool.

Strategy per URL (matches the spec's Web Page Reader agent):
    1. Try ``requests`` + BeautifulSoup parsing.
    2. If the page looks JavaScript-rendered (very little text) and Playwright
       is installed, re-render it with headless Chromium.
    3. Never fail hard: return a structured dict with ``ok=False`` + ``error``.

The scraper never invents content — it returns exactly what the page contains.
"""

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.config import settings
from app.tools.site_registry import looks_like_navigation

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_TEXT_CAP = 12000
_JS_TEXT_THRESHOLD = 400  # chars below which we suspect JS-only rendering


def _parse_html(html: str, base_url: str) -> Dict[str, Any]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip() or title

    site_name = ""
    og_site = soup.find("meta", attrs={"property": "og:site_name"})
    if og_site and og_site.get("content"):
        site_name = og_site["content"].strip()
    if not site_name:
        site_name = urlparse(base_url).netloc.removeprefix("www.")

    meta_description = ""
    for meta in soup.find_all("meta"):
        if (meta.get("name") or "").lower() in ("description", "og:description") and meta.get("content"):
            meta_description = meta["content"].strip()
            break

    # Collect same-page links (absolute) before decomposing nav elements.
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"].strip())
        if href.startswith(("http://", "https://")):
            links.append(href.split("#")[0])
    links = list(dict.fromkeys(links))

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "iframe", "form", "button"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.body or soup
    text = main.get_text(separator="\n", strip=True)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())[:_TEXT_CAP]

    return {
        "title": title,
        "site_name": site_name,
        "meta_description": meta_description,
        "text": text,
        "links": links,
    }
def _render_with_playwright(url: str) -> Optional[str]:
    """Optional JS rendering. Returns HTML or None when unavailable/failed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("[Scraper] Playwright not installed — skipping JS rendering for %s", url)
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            page.goto(url, timeout=settings.request_timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)  # let SPA content settle
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        logger.warning("[Scraper] Playwright render failed for %s: %s", url, e)
        return None


def scrape_page(url: str, timeout: Optional[int] = None) -> Dict[str, Any]:
    """Fetch and parse a webpage. Returns a structured page dict (never raises)."""
    timeout = timeout or settings.request_timeout
    result: Dict[str, Any] = {
        "ok": False,
        "url": url,
        "final_url": url,
        "status": 0,
        "title": "",
        "site_name": "",
        "meta_description": "",
        "text": "",
        "links": [],
        "rendered_with": "requests",
        "error": None,
    }
    try:
        response = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        result["status"] = response.status_code
        result["final_url"] = response.url
        response.raise_for_status()
        result.update(_parse_html(response.text, response.url))

        if len(result["text"]) < _JS_TEXT_THRESHOLD:
            html = _render_with_playwright(url)
            if html:
                result.update(_parse_html(html, url))
                result["rendered_with"] = "playwright"

        result["ok"] = len(result["text"]) > 100 or bool(result["title"])
        if not result["ok"]:
            result["error"] = "page returned no usable content (possibly JS-only or blocked)"
    except Exception as e:
        result["error"] = str(e)
        logger.warning("[Scraper] Failed to scrape %s: %s", url, e)
    return result


def extract_detail_links(page: Dict[str, Any], site: Dict[str, Any], cap: int = 8) -> List[str]:
    """Pull candidate opportunity detail URLs out of a scraped listing page.

    Only same-domain links that look like detail pages are returned.
    """
    from app.tools.site_registry import is_detail_url

    base_domain = urlparse(page.get("final_url") or page.get("url") or "").netloc
    listing_url = str(site.get("listing_url") or "")
    out: List[str] = []
    for link in page.get("links", []):
        if looks_like_navigation(link):
            continue
        if urlparse(link).netloc != base_domain:
            continue
        if link == listing_url or link.rstrip("/") == listing_url.rstrip("/"):
            continue  # self-link back to the listing page
        if is_detail_url(link, site) and link not in out:
            out.append(link)
        if len(out) >= cap:
            break
    return out


