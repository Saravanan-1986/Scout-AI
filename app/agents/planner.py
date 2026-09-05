"""Planner Agent (Agent 1).

Understands the student profile and dynamically creates a site-restricted
search strategy. On round 2+ it receives the quality evaluator's feedback and
generates DIFFERENT queries instead of repeating the failed ones.
"""

import logging
from typing import Any, Dict, List

from app.config import settings
from app.graph import trace
from app.llm import call_llm, llm_available
from app.tools.site_registry import get_sites

logger = logging.getLogger(__name__)

_TYPE_LABELS = {"internship": "internships", "hackathon": "hackathons", "both": "internships AND hackathons/coding competitions"}


def _requested_types(search_type: str) -> List[str]:
    stype = (search_type or "both").lower()
    if stype == "internship":
        return ["internship"]
    if stype in ("hackathon", "hackathons", "competition"):
        return ["hackathon", "coding_competition"]
    return ["internship", "hackathon", "coding_competition"]


def _fallback_queries(profile: Dict[str, Any], search_type: str, iteration: int) -> List[str]:
    """Profile-derived queries (no LLM needed). Templates rotate per round."""
    skills = [s for s in (profile.get("skills") or profile.get("programming_languages") or []) if s]
    skill = skills[0] if skills else "software"
    interest = (profile.get("interests") or ["technology"])[0]
    dept = profile.get("department") or "computer science"
    year = profile.get("year") or 3
    types = _requested_types(search_type)

    queries: List[str] = []
    if "internship" in types:
        pool_a = [
            f"{skill} {dept} internship for engineering students india 2026",
            f"{interest} internship {year}rd year student stipend india",
            f"software development internship {year} year college student remote india",
        ]
        pool_b = [
            f"{dept} student summer internship india apply",
            f"{skill} internship opening for undergraduates india",
            f"paid technical internship {year} year {dept} students india",
        ]
        queries += pool_a if iteration % 2 == 1 else pool_b
    if any(t in types for t in ("hackathon", "coding_competition")):
        pool_a = [
            f"{interest} hackathon 2026 india students",
            f"coding competition 2026 college students india",
            f"online {skill} hackathon register 2026",
        ]
        pool_b = [
            f"student technical competition {year} year india 2026",
            f"{skill} hackathon india students apply deadline",
            f"national level coding contest college students 2026",
        ]
        queries += pool_a if iteration % 2 == 1 else pool_b
    return queries


def planner_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate dynamic, profile-driven search queries for this round."""
    profile = state.get("student_profile", {})
    search_type = state.get("search_type", "both")
    iteration = state.get("iteration", 1)
    used = list(state.get("used_queries", []))
    quality = state.get("quality") or {}

    allowed_domains = sorted({s["domain"] for s in get_sites(search_type)})

    prompt = (
        "You are the Planner Agent of ScoutAI, a research agent that finds internships, "
        "hackathons and coding competitions for college students.\n\n"
        f"STUDENT PROFILE:\n"
        f"- Degree/Department: {profile.get('degree', '')} {profile.get('department', '')}\n"
        f"- Year of study: {profile.get('year', '')}\n"
        f"- CGPA: {profile.get('cgpa', '')}\n"
        f"- Skills: {', '.join(profile.get('skills') or [])}\n"
        f"- Languages: {', '.join(profile.get('programming_languages') or [])}\n"
        f"- Technologies: {', '.join(profile.get('technologies') or [])}\n"
        f"- Interests: {', '.join(profile.get('interests') or [])}\n"
        f"- Preferred locations: {', '.join(profile.get('preferred_locations') or [])}\n\n"
        f"REQUESTED OPPORTUNITY TYPES: {_TYPE_LABELS.get((search_type or 'both').lower(), search_type)}\n"
        f"The results will be filtered to these websites only: {', '.join(allowed_domains)}\n\n"
        f"Generate {settings.max_queries_per_round} search queries a search engine can use "
        f"to find CURRENT, real opportunity pages on those websites "
        f"(mention topic, opportunity type, 'students', 'India' and the year where natural).\n"
    )
    if iteration > 1 or quality:
        previous = used or quality.get("attempted_queries") or []
        prompt += (
            f"\nIMPORTANT: round {iteration}. These previous queries produced insufficient results: "
            f"{'; '.join(previous)}\n"
            f"Feedback: {quality.get('reason', 'insufficient verified results')}.\n"
            "Generate COMPLETELY DIFFERENT queries with new angles (different skills, formats, phrasing).\n"
        )
    prompt += "\nOutput ONLY the query strings, one per line, no numbering or bullets."

    queries: List[str] = []
    if llm_available():
        raw = call_llm(prompt, temperature=0.6)
        if raw:
            queries = [
                line.strip().strip("-*1234567890. ").strip()
                for line in raw.strip().splitlines()
                if line.strip() and len(line.strip()) > 8
            ]
    if not queries:
        queries = _fallback_queries(profile, search_type, iteration)

    # Deduplicate against everything already tried this run.
    fresh = []
    for q in queries:
        ql = q.lower()
        if ql not in {u.lower() for u in used} and q not in fresh:
            fresh.append(q)
    queries = fresh[: settings.max_queries_per_round]

    trace.record("planner", f"round {iteration}: generated {len(queries)} search queries", queries=queries)
    logger.info("[Planner] Round %s queries: %s", iteration, queries)

    return {
        "search_queries": queries,
        "used_queries": used + queries,
        "iteration": iteration,
    }

