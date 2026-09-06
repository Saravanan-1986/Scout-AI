"""Whitelisted discovery sources for ScoutAI.

The agent is ONLY allowed to search and scrape these domains. This is what
guarantees results come from real student-opportunity platforms instead of
random web pages that happen to contain matching keywords.
"""

from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# Internship sources
# --------------------------------------------------------------------------- #
INTERNSHIP_SITES: List[Dict[str, object]] = [
    {
        "domain": "internshala.com",
        "name": "Internshala",
        "listing_url": "https://internshala.com/internships/",
        "detail_patterns": ["/internship/detail", "/internships/detail"],
        "default_type": "internship",
        "priority": 1,
    },
    {
        "domain": "unstop.com",
        "name": "Unstop",
        "listing_url": "https://unstop.com/internships",
        "detail_patterns": ["/internships/"],
        "default_type": "internship",
        "priority": 2,
    },
    {
        "domain": "linkedin.com",
        "name": "LinkedIn Jobs",
        "listing_url": "https://www.linkedin.com/jobs/",
        "detail_patterns": ["/jobs/view/"],
        "default_type": "internship",
        "priority": 6,
    },
    {
        "domain": "in.indeed.com",
        "name": "Indeed India",
        "listing_url": "https://in.indeed.com/jobs?q=internship",
        "detail_patterns": ["/viewjob", "/cmp/"],
        "default_type": "internship",
        "priority": 6,
    },
    {
        "domain": "wellfound.com",
        "name": "Wellfound",
        "listing_url": "https://wellfound.com/jobs",
        "detail_patterns": ["/role/", "/jobs/"],
        "default_type": "internship",
        "priority": 5,
    },
    {
        "domain": "naukri.com",
        "name": "Naukri",
        "listing_url": "https://www.naukri.com/internship-jobs",
        "detail_patterns": ["-job-", "/job-listings-"],
        "default_type": "internship",
        "priority": 5,
    },
    {
        "domain": "internship.aicte-india.org",
        "name": "AICTE Internship Portal",
        "listing_url": "https://internship.aicte-india.org/",
        "detail_patterns": ["/internship", "/detail"],
        "default_type": "internship",
        "priority": 3,
    },
]

# --------------------------------------------------------------------------- #
# Hackathon / competition sources
# --------------------------------------------------------------------------- #
COMPETITION_SITES: List[Dict[str, object]] = [
    {
        "domain": "devpost.com",
        "name": "Devpost",
        "listing_url": "https://devpost.com/hackathons",
        "detail_patterns": ["/hackathons/"],
        "default_type": "hackathon",
        "priority": 1,
    },
    {
        "domain": "unstop.com",
        "name": "Unstop",
        "listing_url": "https://unstop.com/hackathons",
        "detail_patterns": ["/hackathons/", "/competitions/"],
        "default_type": "hackathon",
        "priority": 2,
    },
    {
        "domain": "hackerearth.com",
        "name": "HackerEarth",
        "listing_url": "https://www.hackerearth.com/challenges/",
        "detail_patterns": ["/challenges/", "/hackathons/"],
        "default_type": "hackathon",
        "priority": 2,
    },
    {
        "domain": "devfolio.co",
        "name": "Devfolio",
        "listing_url": "https://devfolio.co/hackathons",
        "detail_patterns": ["/hackathons/"],
        "default_type": "hackathon",
        "priority": 3,
    },
    {
        "domain": "mlh.io",
        "name": "MLH",
        "listing_url": f"https://mlh.io/seasons/{datetime.now().year}/events",
        "detail_patterns": ["/event", "/events/"],
        "default_type": "hackathon",
        "priority": 2,
    },
    {
        "domain": "codechef.com",
        "name": "CodeChef",
        "listing_url": "https://www.codechef.com/contests",
        "detail_patterns": ["/contests/"],
        "default_type": "coding_competition",
        "priority": 4,
    },
    {
        "domain": "hackerrank.com",
        "name": "HackerRank",
        "listing_url": "https://www.hackerrank.com/contests",
        "detail_patterns": ["/contests/"],
        "default_type": "coding_competition",
        "priority": 4,
    },
]

_ALL_SITES: Dict[str, Dict[str, object]] = {}
for _site in INTERNSHIP_SITES + COMPETITION_SITES:
    _ALL_SITES[_site["domain"]] = _site  # unstop.com appears in both lists; first listing wins

_NAV_HINTS = (
    "?page=", "/search", "/tag/", "/category/", "/categories/", "/topics/",
    "/about", "/blog", "/faq", "/privacy", "/terms", "/login", "/signin",
    "/signup", "/register", "/registration", "/jobs?", "/explore", "/company/", "/campus/",
    "utm_", "/ref/", "/feed", "/user/", "/profile", "/leaderboard", "/learn",
    "/college/", "/community", "/courses", "/settings", "/jobs/", "share", "/onboarding",
)


def get_sites(search_type: str) -> List[Dict[str, object]]:
    """Return whitelisted site descriptors for the requested search type."""
    stype = (search_type or "both").lower()
    if stype == "internship":
        return sorted(INTERNSHIP_SITES, key=lambda s: s["priority"])
    if stype in ("hackathon", "competition", "hackathons"):
        return sorted(COMPETITION_SITES, key=lambda s: s["priority"])
    seen, merged = set(), []
    for site in sorted(INTERNSHIP_SITES + COMPETITION_SITES, key=lambda s: s["priority"]):
        key = (site["domain"], site["listing_url"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(site)
    return merged


def _host_matches(host: str, domain: str) -> bool:
    host = host.lower().removeprefix("www.")
    return host == domain.lower() or host.endswith("." + domain.lower())


def site_for_url(url: str) -> Optional[Dict[str, object]]:
    """Return the whitelisted site descriptor for a URL, or None if not allowed."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    if not host:
        return None
    for domain, site in _ALL_SITES.items():
        if _host_matches(host, domain):
            return site
    return None


def is_allowed_url(url: str) -> bool:
    """True when the URL belongs to one of the whitelisted sources."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    return site_for_url(url) is not None


def is_detail_url(url: str, site: Dict[str, object]) -> bool:
    """Heuristically decide whether a URL looks like an opportunity detail page."""
    path = urlparse(url).path.lower()
    for pattern in (site.get("detail_patterns") or []):
        if pattern.lower() in path:
            return True
    segments = [seg for seg in path.split("/") if seg]
    return len(segments) >= 2 and not any(hint in url.lower() for hint in _NAV_HINTS)


def looks_like_navigation(url: str) -> bool:
    """Filter out obvious navigation / metadata / asset links."""
    lowered = url.lower()
    if any(hint in lowered for hint in _NAV_HINTS):
        return True
    if lowered.endswith((".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js", ".ico", ".zip")):
        return True
    if lowered.endswith(("#", "/")) and lowered.count("/") <= 3:
        # Bare domain root — that's the listing page itself, not a detail page.
        return True
    return False


# Exact aggregate/category paths per domain (a URL matching one of these is a
# LIST of opportunities, never a single opportunity).
_AGGREGATE_EXACT_PATHS = {
    "unstop.com": ["/internships", "/hackathons", "/competitions"],
    "devpost.com": ["/hackathons"],
    "devfolio.co": ["/hackathons"],
    "codechef.com": ["/contests"],
    "hackerrank.com": ["/contests"],
    "linkedin.com": ["/jobs"],
    "in.indeed.com": ["/jobs"],
    "wellfound.com": ["/jobs"],
    "naukri.com": ["/internship-jobs"],
    "hackerearth.com": ["/challenges"],
    "mlh.io": ["/events"],
    "internship.aicte-india.org": ["/", "/internship"],
}


def is_aggregate_url(url: str, site: Dict[str, object]) -> bool:
    """True when the URL is a listing/category page, not a single opportunity."""
    try:
        path = urlparse(url).path.rstrip("/") or "/"
    except Exception:
        return False
    domain = str(site.get("domain", ""))

    if domain == "internshala.com":
        # Real Internshala detail pages live under /internship/detail/...
        # Everything else under /internships/... is a category list.
        return path.startswith("/internships/") and "/internship/detail" not in path

    if domain == "mlh.io":
        return "/seasons/" in path or path.endswith("/events")

    if domain == "hackerearth.com":
        # /challenges/ and /challenges/<category>/ are lists; a real
        # challenge has at least 3 path segments.
        segments = [seg for seg in path.split("/") if seg]
        return len(segments) <= 2

    for aggregate in _AGGREGATE_EXACT_PATHS.get(domain, []):
        if path == aggregate or path.startswith(aggregate + "/"):
            # e.g. /jobs or /jobs/search -> aggregate
            return True
    return False

