"""Quality Evaluator — decides whether the agent has enough relevant results.

This is what makes ScoutAI agentic: if the collected, verified, relevant
opportunities are insufficient, the graph loops back to the Planner to search
again with different queries (bounded by ``settings.max_iterations``).
"""

import logging
from typing import Any, Dict

from app.config import settings
from app.graph import trace

logger = logging.getLogger(__name__)


def _requested_types(search_type: str) -> set:
    stype = (search_type or "both").lower()
    if stype == "internship":
        return {"internship"}
    if stype in ("hackathon", "hackathons", "competition"):
        return {"hackathon", "coding_competition"}
    return {"internship", "hackathon", "coding_competition"}


def quality_evaluator_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    opportunities = list(state.get("eligible_opportunities", []))
    iteration = state.get("iteration", 1)
    allowed_types = _requested_types(state.get("search_type", "both"))

    relevant = [
        o for o in opportunities
        if o.get("type") in allowed_types and o.get("eligibility_status") != "NOT ELIGIBLE"
    ]
    verified = [o for o in relevant if o.get("verified")]
    eligible = [o for o in relevant if o.get("eligibility_status") == "ELIGIBLE"]

    enough = len(verified) >= settings.min_results
    can_replan = iteration < settings.max_iterations
    should_replan = not enough and can_replan

    if enough:
        reason = f"{len(verified)} verified relevant opportunities reached the target of {settings.min_results}."
    elif can_replan:
        reason = (
            f"Only {len(verified)} verified relevant opportunities (target {settings.min_results}). "
            f"Asking the planner for a different search strategy."
        )
    else:
        reason = (
            f"Only {len(verified)} verified relevant opportunities, but the maximum of "
            f"{settings.max_iterations} planning rounds has been reached — proceeding with what was found."
        )

    quality = {
        "total_found": len(opportunities),
        "relevant": len(relevant),
        "verified_relevant": len(verified),
        "eligible": len(eligible),
        "enough": enough,
        "should_replan": should_replan,
        "reason": reason,
    }
    trace.record(
        "quality_evaluator",
        "evaluated result quality: " + ("enough results" if enough else ("re-planning needed" if should_replan else "max rounds reached")),
        relevant=len(relevant),
        verified=len(verified),
        eligible=len(eligible),
        decision="search again" if should_replan else "finalize recommendations",
    )
    logger.info("[Quality] %s", quality)

    return {
        "quality": quality,
        "iteration": iteration + 1 if should_replan else iteration,
    }


def route_after_quality(state: Dict[str, Any]) -> str:
    """LangGraph conditional edge: loop back to the planner or finish."""
    quality = state.get("quality") or {}
    return "replan" if quality.get("should_replan") else "finish"
