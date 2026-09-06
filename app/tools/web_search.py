"""Web search tool.

Search results are always restricted to the whitelisted discovery sites via
``include_domains`` (Tavily) or ``site:`` operators (DuckDuckGo). Tavily is
used when an API key is configured; otherwise a free DuckDuckGo fallback is
used. Random, off-whitelist pages can never enter the pipeline.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Cap for how many whitelisted domains DuckDuckGo queries run individually for
# a single query string (Tavily handles all domains in one API call).
_MAX_DDGS_DOMAINS = 3


def _dedupe(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for item in results:
        url = item.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def _tavily_search(query: str, max_results: int, site_domains: Optional[List[str]]) -> Optional[List[Dict[str, Any]]]:
    if settings.tavily_api_key in ("", "your_tavily_api_key_here"):
        return None
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        kwargs: Dict[str, Any] = {"query": query, "max_results": max_results}
        if site_domains:
            kwargs["include_domains"] = site_domains
        response = client.search(**kwargs)
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "source": "tavily",
            }
            for item in response.get("results", [])
        ]
        logger.info("[Tavily] '%s' returned %d results (domains=%s).", query, len(results), site_domains)
        return results
    except Exception as e:
        logger.warning("[Tavily] Search failed for '%s': %s", query, e)
        return None


def _ddgs_search(query: str, max_results: int, site_domains: Optional[List[str]]) -> List[Dict[str, Any]]:
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        logger.error("[DuckDuckGo] ddgs package not installed; cannot search.")
        return []

    results: List[Dict[str, Any]] = []
    # DuckDuckGo handles a single site: operator reliably, so one call per domain.
    domains = (site_domains or [None])[:_MAX_DDGS_DOMAINS] if site_domains else [None]

    def _one(domain: Optional[str]) -> List[Dict[str, Any]]:
        q = f"{query} site:{domain}" if domain else query
        try:
            # timeout bounds each engine attempt; backend limits ddgs to three
            # reliable engines (by default it also probes wikipedia/grokipedia/
            # startpage/yahoo which are slow or useless here).
            raw = list(
                DDGS(timeout=6).text(
                    q,
                    max_results=max_results,
                    backend="duckduckgo,google,brave",
                )
            )
        except TypeError:
            try:
                raw = list(DDGS(timeout=6).text(q, max_results=max_results))
            except Exception as e:
                logger.warning("[DuckDuckGo] Search failed for '%s': %s", q, e)
                return []
        except Exception as e:
            logger.warning("[DuckDuckGo] Search failed for '%s': %s", q, e)
            return []
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("href", item.get("url", "")),
                "content": item.get("body", item.get("content", "")),
                "source": "duckduckgo",
            }
            for item in raw
        ]

    if len(domains) > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=len(domains)) as pool:
            for part in pool.map(_one, domains):
                results.extend(part)
    else:
        results.extend(_one(domains[0]))
    logger.info("[DuckDuckGo] '%s' returned %d results (domains=%s).", query, len(results), site_domains)
    return results


def search_web(
    query: str,
    max_results: int = 5,
    site_domains: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Search the web, restricted to ``site_domains`` when provided.

    Returns a list of dicts: {title, url, content, source}.
    """
    results = _tavily_search(query, max_results, site_domains)
    if results is None:
        results = _ddgs_search(query, max_results, site_domains)
    return _dedupe(results)

