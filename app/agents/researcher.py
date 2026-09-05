"""Researcher Agent (Agent 2 + 3): web search, scraping and extraction.

Everything is restricted to the whitelisted discovery sites:
    1. Directly scrape the listing pages of relevant whitelisted sites and
       harvest opportunity detail links.
    2. Run the planner's queries through the web-search tool, restricted to
       whitelisted domains only.
    3. Rank, deduplicate and scrape the most promising detail pages.
    4. Extract structured opportunities — anything not on the page stays
       "Not specified". Fabricated fallback opportunities are gone.

Re-planning rounds skip already-processed URLs and merge into existing results.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.config import settings
from app.graph import trace
from app.tools.opportunity_extractor import extract_opportunity
from app.tools.site_registry import get_sites, is_detail_url, site_for_url
from app.tools.web_scraper import extract_detail_links, scrape_page
from app.tools.web_search import search_web

logger = logging.getLogger(__name__)


def _requested_types(search_type: str) -> set:
    stype = (search_type or "both").lower()
    if stype == "internship":
        return {"internship"}
    if stype in ("hackathon", "hackathons", "competition"):
        return {"hackathon", "coding_competition"}
    return {"internship", "hackathon", "coding_competition"}


def _opp_key(opp: Dict[str, Any]) -> tuple:
    domain = urlparse(opp.get("source_url") or "").netloc.removeprefix("www.")
    return (opp.get("title", "").lower().strip(), domain)


def _candidate_score(url: str, via: str) -> int:
    score = 1
    site = site_for_url(url)
    if site and is_detail_url(url, site):
        score += 2
    if via == "search":
        score += 1
    return score
def _discover_from_listings(sites: List[Dict[str, Any]], candidates: Dict[str, Dict[str, Any]], errors: List[str]) -> None:
    """Scrape each whitelisted listing page and harvest detail links."""
    for site in sites:
        listing = str(site["listing_url"])
        page = scrape_page(listing)
        if not page.get("ok"):
            errors.append(f"listing {listing}: {page.get('error')}")
            trace.record(
                "researcher",
                f"listing scan failed: {site['name']}",
                url=listing,
                error=page.get("error"),
            )
            continue
        links = extract_detail_links(page, site, cap=settings.max_pages_per_source)
        added = 0
        for link in links:
            if link not in candidates:
                candidates[link] = {
                    "title": "",
                    "snippet": "",
                    "source_name": site["name"],
                    "site": site,
                    "via": "listing",
                }
                added += 1
        trace.record(
            "researcher",
            f"listing scan: {site['name']}",
            url=listing,
            detail_links_found=len(links),
            new_candidates=added,
        )


def _discover_from_search(
    queries: List[str],
    sites: List[Dict[str, Any]],
    candidates: Dict[str, Dict[str, Any]],
    raw_results: List[Dict[str, Any]],
    errors: List[str],
) -> None:
    """Run each planned query restricted to whitelisted domains."""
    domains = [str(s["domain"]) for s in sites]
    results: List[Dict[str, Any]] = []
    for i, query in enumerate(queries):
        results = search_web(query, max_results=settings.max_search_results, site_domains=domains)
        raw_results.extend(results)
        kept = 0
        for item in results:
            url = item.get("url") or ""
            site = site_for_url(url)
            if not site or url in candidates:
                continue
            candidates[url] = {
                "title": item.get("title", ""),
                "snippet": item.get("content", ""),
                "source_name": site["name"],
                "site": site,
                "via": "search",
            }
            kept += 1
        trace.record(
            "researcher",
            "web search",
            query=query,
            results_found=len(results),
            new_candidates=kept,
        )
        if i < len(queries) - 1 and settings.search_delay_seconds > 0:
            time.sleep(settings.search_delay_seconds)
    if not results and queries:
        errors.append("web search returned no results (search provider may be rate-limited)")
def researcher_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Search whitelisted sites, scrape detail pages and extract opportunities."""
    queries = list(state.get("search_queries") or [])
    search_type = state.get("search_type", "both")
    iteration = state.get("iteration", 1)
    existing = list(state.get("scraped_opportunities", []))
    processed = set(state.get("processed_urls", []))
    raw_results = list(state.get("raw_search_results", []))
    errors = list(state.get("errors", []))
    allowed_types = _requested_types(search_type)
    sites = get_sites(search_type)

    trace.record(
        "researcher",
        f"round {iteration}: starting research",
        queries=len(queries),
        whitelisted_sites=[str(s["name"]) for s in sites],
        already_processed=len(processed),
    )

    # ---------------- 1 + 2. Discovery ----------------
    candidates: Dict[str, Dict[str, Any]] = {}
    _discover_from_listings(sites, candidates, errors)
    _discover_from_search(queries, sites, candidates, raw_results, errors)
    candidates = {u: c for u, c in candidates.items() if u not in processed}

    # ---------------- 3. Rank and scrape ----------------
    ranked_urls = sorted(candidates, key=lambda u: _candidate_score(u, candidates[u]["via"]), reverse=True)
    selected = ranked_urls[: settings.max_pages_per_round]
    trace.record(
        "researcher",
        f"selecting {len(selected)} of {len(candidates)} candidate pages to read",
    )

    new_opportunities: List[Dict[str, Any]] = []
    existing_keys = {_opp_key(o) for o in existing}
    existing_urls = {o.get("source_url") for o in existing}

    for url in selected:
        info = candidates[url]
        site = info["site"]
        page = scrape_page(url)
        processed.add(url)
        if not page.get("ok") and not page.get("title"):
            errors.append(f"scrape {url}: {page.get('error')}")
            trace.record("researcher", "page unreadable — skipped", url=url, error=page.get("error"))
            continue

        opp = extract_opportunity(page, site, snippet=info["snippet"])
        if opp is None:
            trace.record("researcher", "no opportunity content found — skipped", url=url)
            continue

        if opp["type"] not in allowed_types:
            trace.record(
                "researcher",
                "type mismatch — skipped",
                title=opp["title"],
                page_type=opp["type"],
            )
            continue

        key = _opp_key(opp)
        if key in existing_keys or opp["source_url"] in existing_urls:
            trace.record("researcher", "duplicate — skipped", title=opp["title"])
            continue

        new_opportunities.append(opp)
        existing_keys.add(key)
        existing_urls.add(opp["source_url"])
        trace.record(
            "researcher",
            "extracted opportunity",
            title=opp["title"],
            type=opp["type"],
            source=opp["source_name"],
            verified=opp["verified"],
        )

    all_opportunities = existing + new_opportunities
    trace.record(
        "researcher",
        f"round {iteration} complete: {len(new_opportunities)} new, {len(all_opportunities)} total opportunities",
    )
    logger.info("[Researcher] Round %s: +%d opportunities (total %d)", iteration, len(new_opportunities), len(all_opportunities))

    return {
        "raw_search_results": raw_results,
        "processed_urls": sorted(processed),
        "scraped_opportunities": all_opportunities,
        "errors": errors,
    }


