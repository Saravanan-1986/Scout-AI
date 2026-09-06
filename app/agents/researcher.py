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
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.config import settings
from app.graph import trace
from app.tools import opp_cache
from app.tools.freshness import check_freshness, deadline_is_past, years_in_url
from app.tools.opportunity_extractor import extract_opportunity, looks_like_aggregate_title
from app.tools.site_registry import (
    get_sites,
    is_aggregate_url,
    is_detail_url,
    looks_like_navigation,
    site_for_url,
)
from app.tools.web_scraper import extract_detail_links, scrape_page, scrape_urls_concurrent
from app.tools.web_search import search_web

logger = logging.getLogger(__name__)


def _url_fresh(url: str, today: Optional[date] = None) -> bool:
    """Cheap pre-scrape check: skip URLs that point to past editions."""
    years = years_in_url(url)
    today = today or date.today()
    return not years or max(years) >= today.year


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


_JUNK_TITLE_RE = re.compile(
    r"^(home|login|sign ?up|sign ?in|about( us)?|contact( us)?|faq|help|privacy|terms|"
    r"for business|business|manage contests|contests|hackathons|internships|jobs|"
    r"explore|search|dashboard|profile|settings|notifications|messages|blog|pricing)$",
    re.IGNORECASE,
)


def _plausible_opportunity(opp: Dict[str, Any], page: Dict[str, Any]) -> bool:
    """Final quality gate: reject pages that are clearly NOT an opportunity.

    Defense in depth for pages that slipped past the URL filters (e.g. SPA
    navigation links rendered on listing pages). A real opportunity page has
    either a concrete field (deadline/stipend/prize/duration) or clear
    apply/register language in its text.
    """
    title = str(opp.get("title") or "").strip()
    if not title or len(title) < 8 or _JUNK_TITLE_RE.match(title):
        return False
    org = str(opp.get("organization") or "").strip().lower()
    if org and title.lower() in {org, org.split(".")[0], f"the {org}"}:
        return False  # page title is just the site name
    text = str(page.get("text") or "").lower()
    has_field = any(
        str(opp.get(f) or "Not specified") not in ("", "Not specified", None)
        for f in ("deadline", "stipend", "prize", "duration")
    )
    has_action = any(
        k in text
        for k in (
            "apply now", "apply by", "how to apply", "register", "last date",
            "stipend", "prize pool", "eligibility", "apply link", "application deadline",
        )
    )
    # Long, substantive titles on an official detail URL are almost certainly
    # real opportunities even when the extracted text lacks the exact action
    # keywords (the text cap may have cut them off).
    if len(title) >= 20 and " " in title.strip():
        return True
    return has_field or has_action


def _candidate_score(url: str, via: str) -> int:
    score = 1
    site = site_for_url(url)
    if site and is_detail_url(url, site):
        score += 2
    if via == "search":
        score += 1
    return score
def _discover_from_listings(sites: List[Dict[str, Any]], candidates: Dict[str, Dict[str, Any]], errors: List[str]) -> None:
    """Scrape all whitelisted listing pages CONCURRENTLY, then harvest detail links."""
    today = date.today()

    def _scan(site: Dict[str, Any]):
        listing = str(site["listing_url"])
        return site, listing, scrape_page(listing)

    workers = max(1, min(len(sites), settings.scrape_workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for site, listing, page in pool.map(_scan, sites):
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
            added = stale = 0
            for link in links:
                if not _url_fresh(link, today):
                    stale += 1  # past edition (e.g. .../hackathon-2025) — don't even scrape
                    continue
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
                stale_skipped=stale,
            )


def _discover_from_search(
    queries: List[str],
    sites: List[Dict[str, Any]],
    candidates: Dict[str, Dict[str, Any]],
    raw_results: List[Dict[str, Any]],
    errors: List[str],
) -> None:
    """Run every planned query CONCURRENTLY, restricted to whitelisted domains."""
    domains = [str(s["domain"]) for s in sites]
    today = date.today()

    def _run(query: str):
        return query, search_web(query, max_results=settings.max_search_results, site_domains=domains)

    any_results = False
    workers = max(1, min(len(queries), 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for query, results in pool.map(_run, queries):
            raw_results.extend(results)
            any_results = any_results or bool(results)
            kept = stale = 0
            for item in results:
                url = item.get("url") or ""
                site = site_for_url(url)
                if not site or url in candidates or looks_like_navigation(url):
                    continue
                # Accept detail pages AND listing/category pages from search.
                # Detail pages become direct opportunities; listing pages get
                # scraped and drilled into detail links (aggregate handling).
                if not (is_detail_url(url, site) or is_aggregate_url(url, site)):
                    continue
                if not _url_fresh(url, today):
                    stale += 1
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
                stale_skipped=stale,
            )
    if not any_results and queries:
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

    def _accept(opp: Dict[str, Any]) -> bool:
        """Deduplicate, record and cache an accepted opportunity."""
        key = _opp_key(opp)
        if key in existing_keys or opp.get("source_url") in existing_urls:
            trace.record("researcher", "duplicate — skipped", title=opp.get("title"))
            return False
        new_opportunities.append(opp)
        existing_keys.add(key)
        existing_urls.add(opp.get("source_url"))
        opp_cache.cache_opportunity(opp)  # future runs skip re-scraping this page
        trace.record(
            "researcher",
            "extracted opportunity",
            title=opp["title"],
            type=opp["type"],
            source=opp["source_name"],
            verified=opp["verified"],
        )
        return True

    # ---------------- 4. BFS: read pages, drill into specifics ----------------
    # When a page is an AGGREGATE listing ("Find 34 Data Structures
    # Internships"), it is NOT recorded as an opportunity — instead its
    # detail links are queued and scraped, so the results are specific
    # per-company opportunities, not category pages.
    queue: List[str] = ranked_urls[: settings.max_pages_per_round]
    scraped_count = 0

    # Pages are processed in CONCURRENT batches (Bottleneck #1): scrape N
    # pages in parallel, extract their opportunities in parallel (the LLM
    # refinement is network I/O), then post-process in original order.
    while queue and scraped_count < settings.max_pages_per_round:
        batch: List[str] = []
        while (
            queue
            and len(batch) < settings.scrape_workers
            and scraped_count + len(batch) < settings.max_pages_per_round
        ):
            nxt = queue.pop(0)
            if nxt in processed or nxt not in candidates:
                continue
            batch.append(nxt)
        if not batch:
            break

        # ---- MongoDB opportunity cache: skip the network entirely ----
        to_scrape: List[str] = []
        for url in batch:
            cached = opp_cache.get_cached_opportunity(url)
            if cached is None:
                to_scrape.append(url)
                continue
            processed.add(url)
            scraped_count += 1
            if not _plausible_opportunity(cached, {"text": ""}):
                trace.record(
                    "researcher", "cached junk page — skipped", url=url,
                    title=cached.get("title"),
                )
                continue
            trace.record(
                "researcher",
                "cache hit — reused recent scrape",
                url=url,
                source=cached.get("source_name"),
            )
            if deadline_is_past(cached.get("deadline")):
                trace.record(
                    "researcher", "stale/expired — skipped", url=url,
                    reason=f"stated deadline has passed ({cached.get('deadline')})",
                )
                continue
            if cached.get("type") not in allowed_types:
                trace.record(
                    "researcher", "type mismatch — skipped",
                    title=cached.get("title"), page_type=cached.get("type"),
                )
                continue
            _accept(cached)

        if not to_scrape:
            continue

        # ---- Concurrent scrape, then concurrent (LLM) extraction ----
        pages = scrape_urls_concurrent(to_scrape)

        def _extract(item):
            url, cand, page = item
            page_title = str(page.get("title") or "").strip()
            if is_aggregate_url(url, cand["site"]) or looks_like_aggregate_title(page_title):
                return None  # aggregate page — it gets drilled, never extracted (no LLM call)
            return extract_opportunity(page, cand["site"], snippet=cand["snippet"])

        triples = [(u, candidates[u], page) for u, page in zip(to_scrape, pages)]
        with ThreadPoolExecutor(max_workers=max(1, min(len(triples), settings.scrape_workers))) as pool:
            extractions = list(pool.map(_extract, triples))

        # ---- Sequential post-processing (deterministic original order) ----
        for url, page, opp in zip(to_scrape, pages, extractions):
            processed.add(url)
            scraped_count += 1
            site = candidates[url]["site"]

            if not page.get("ok") and not page.get("title"):
                errors.append(f"scrape {url}: {page.get('error')}")
                trace.record("researcher", "page unreadable — skipped", url=url, error=page.get("error"))
                continue

            page_title = str(page.get("title") or "").strip()
            follow = extract_detail_links(page, site, cap=settings.max_pages_per_source + 2)

            if is_aggregate_url(url, site) or looks_like_aggregate_title(page_title):
                # Aggregate/category page: follow its real detail links instead.
                added = 0
                for link in follow:
                    if (
                        _url_fresh(link)
                        and is_detail_url(link, site)  # never queue SPA nav/misc links
                        and not is_aggregate_url(link, site)
                        and link not in processed
                        and link not in candidates
                    ):
                        candidates[link] = {
                            "title": "",
                            "snippet": "",
                            "source_name": site["name"],
                            "site": site,
                            "via": "follow",
                        }
                        queue.append(link)
                        added += 1
                    if added >= settings.max_pages_per_source:
                        break
                trace.record(
                    "researcher",
                    "aggregate listing page — drilled into detail pages",
                    url=url,
                    detail_links_found=len(follow),
                    queued=added,
                )
                continue

            if opp is None:
                trace.record("researcher", "no opportunity content found — skipped", url=url)
                continue

            # Freshness gate: skip concluded events / past editions / passed deadlines.
            fresh, reason = check_freshness(
                url,
                f"{page.get('meta_description') or ''}\n{page.get('text') or ''}",
            )
            if not fresh:
                trace.record("researcher", "stale/expired — skipped", url=url, reason=reason)
                continue
            if deadline_is_past(opp.get("deadline")):
                trace.record(
                    "researcher",
                    "stale/expired — skipped",
                    url=url,
                    reason=f"stated deadline has passed ({opp.get('deadline')})",
                )
                continue

            if opp["type"] not in allowed_types:
                trace.record(
                    "researcher",
                    "type mismatch — skipped",
                    title=opp["title"],
                    page_type=opp["type"],
                )
                continue

            if not _plausible_opportunity(opp, page):
                trace.record(
                    "researcher",
                    "not a real opportunity page — skipped",
                    url=url,
                    title=opp.get("title"),
                )
                continue

            _accept(opp)

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


