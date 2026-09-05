import logging
import warnings
from typing import Any, Dict, List
from app.config import settings

logger = logging.getLogger(__name__)

# Suppress ddgs rename warning
warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")


def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Executes web search using Tavily API if key exists, otherwise falls back to free DuckDuckGo search."""
    if settings.tavily_api_key and settings.tavily_api_key != "your_tavily_api_key_here":
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=settings.tavily_api_key)
            response = client.search(query=query, max_results=max_results)
            results = response.get("results", [])
            if results:
                logger.info(f"[Tavily] Search for '{query}' returned {len(results)} results.")
                return [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                    }
                    for item in results
                ]
        except Exception as e:
            logger.warning(f"Tavily search failed for query '{query}': {e}. Falling back to DuckDuckGo.")

    # Fallback to free DuckDuckGo search
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        results = list(DDGS().text(query, max_results=max_results))
        logger.info(f"[DuckDuckGo] Search for '{query}' returned {len(results)} results.")
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("href", item.get("url", "")),
                "content": item.get("body", item.get("content", "")),
            }
            for item in results
        ]
    except Exception as e:
        logger.error(f"DuckDuckGo web search failed for query '{query}': {e}")
        return []
