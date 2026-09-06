"""Web page reader / scraper tool.

Strategy per URL (matches the spec's Web Page Reader agent):
    1. Try ``requests`` + BeautifulSoup parsing.
    2. If the page looks JavaScript-rendered (very little text) and Playwright
       is installed, re-render it with headless Chromium.
    3. Never fail hard: return a structured dict with ``ok=False`` + ``error``.

The scraper never invents content — it returns exactly what the page contains.
"""

import atexit
import copy
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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

_TEXT_CAP = 8000
_JS_TEXT_THRESHOLD = 400  # chars below which we suspect JS-only rendering

# In-memory page cache: re-planning rounds re-read the same listing pages;
# serving them from memory turns a multi-second fetch into microseconds.
_PAGE_CACHE: Dict[str, tuple] = {}
_PAGE_CACHE_TTL = 1800.0  # seconds
_CACHE_LOCK = threading.Lock()

# Persistent Playwright browsers (Bottleneck #2): Chromium is launched ONCE
# per worker and reused for every JS-rendered page instead of a fresh launch
# per URL. Playwright's sync API is thread-bound, so renders run on a small
# DEDICATED pool (3 threads) where each thread owns its own browser instance.
_TLS = threading.local()
_PW_EXECUTOR: Optional[ThreadPoolExecutor] = None
_PW_POOL_SIZE = 3


def _pw_executor() -> ThreadPoolExecutor:
    global _PW_EXECUTOR
    if _PW_EXECUTOR is None:
        _PW_EXECUTOR = ThreadPoolExecutor(
            max_workers=_PW_POOL_SIZE, thread_name_prefix="scoutai-playwright"
        )
    return _PW_EXECUTOR


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
def _get_thread_browser():
    """Return this worker thread's persistent browser (launching it once)."""
    browser = getattr(_TLS, "browser", None)
    if browser is not None:
        return browser
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("[Scraper] Playwright not installed — JS rendering disabled.")
        return None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        _TLS.pw, _TLS.browser = pw, browser
        logger.info(
            "[Scraper] Persistent Chromium launched on %s (reused across pages).",
            threading.current_thread().name,
        )
        return browser
    except Exception as e:
        logger.warning("[Scraper] Chromium launch failed: %s", e)
        return None


def _shutdown_playwright() -> None:
    """Close every thread's browser (on its own thread) at process exit."""

    def _close():
        pw = getattr(_TLS, "pw", None)
        if pw is None:
            return
        browser = getattr(_TLS, "browser", None)
        _TLS.pw, _TLS.browser = None, None
        for closer in (browser, pw):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass

    for _ in range(_PW_POOL_SIZE):
        try:
            _pw_executor().submit(_close).result(timeout=10)
        except Exception:
            pass  # process is exiting anyway


atexit.register(_shutdown_playwright)


def _render_with_playwright(url: str) -> Optional[str]:
    """Optional JS rendering on the dedicated Playwright threads."""

    def _job() -> Optional[str]:
        browser = _get_thread_browser()
        if browser is None:
            return None
        page = None
        try:
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            page.goto(url, timeout=settings.request_timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)  # let SPA content settle
            return page.content()
        except Exception as e:
            logger.warning("[Scraper] Playwright render failed for %s: %s", url, e)
            return None
        finally:
            try:
                if page:
                    page.close()
            except Exception:
                pass

    try:
        return _pw_executor().submit(_job).result(timeout=settings.request_timeout * 2 + 15)
    except Exception as e:
        logger.warning("[Scraper] Playwright job timed out/failed for %s: %s", url, e)
        return None


def scrape_page(url: str, timeout: Optional[int] = None) -> Dict[str, Any]:
    """Fetch and parse a webpage. Returns a structured page dict (never raises)."""
    # Serve recently-fetched pages from the in-memory cache.
    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _PAGE_CACHE.get(url)
        if hit and now - hit[0] < _PAGE_CACHE_TTL:
            logger.debug("[Scraper] cache hit: %s", url)
            return copy.deepcopy(hit[1])
        if hit:
            _PAGE_CACHE.pop(url, None)

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
        elif result["ok"]:
            with _CACHE_LOCK:
                _PAGE_CACHE[url] = (time.monotonic(), copy.deepcopy(result))
    except Exception as e:
        result["error"] = str(e)
        logger.warning("[Scraper] Failed to scrape %s: %s", url, e)
    return result


def scrape_urls_concurrent(urls: List[str], max_workers: Optional[int] = None) -> List[Dict[str, Any]]:
    """Scrape many pages CONCURRENTLY (Bottleneck #1).

    Requests + BeautifulSoup are thread-safe and I/O-bound, so a small thread
    pool cuts total scrape time from N×latency to ~ceil(N/workers)×latency.
    Playwright fallbacks are serialized internally by ``_PW_LOCK``.

    Results keep the same order as ``urls``; failures return ``ok=False``
    page dicts (``scrape_page`` never raises).
    """
    workers = max(1, min(max_workers or settings.scrape_workers, len(urls) or 1))
    if len(urls) <= 1:
        return [scrape_page(u) for u in urls]
    pages: List[Dict[str, Any]] = [{}] * len(urls)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(scrape_page, u): i for i, u in enumerate(urls)}
        for future in futures:
            index = futures[future]
            try:
                pages[index] = future.result()
            except Exception as e:  # belt & braces — scrape_page already guards
                pages[index] = {
                    "ok": False, "url": urls[index], "final_url": urls[index],
                    "status": 0, "title": "", "site_name": "", "meta_description": "",
                    "text": "", "links": [], "rendered_with": "requests", "error": str(e),
                }
    logger.info("[Scraper] Concurrently scraped %d pages with %d workers.", len(urls), workers)
    return pages


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
        low = link.lower()
        if (
            "/cdn-cgi/" in low  # Cloudflare email-protection & friends
            or low.startswith(("mailto:", "tel:", "javascript:", "data:"))
            or low.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".ico", ".pdf", ".zip"))
        ):
            continue  # asset/junk links — never real opportunity pages
        if urlparse(link).netloc != base_domain:
            continue
        if link == listing_url or link.rstrip("/") == listing_url.rstrip("/"):
            continue  # self-link back to the listing page
        if is_detail_url(link, site) and link not in out:
            out.append(link)
        if len(out) >= cap:
            break
    return out


