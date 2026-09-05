"""Eligibility Agent (Agent 4).

Compares the student profile against each opportunity's stated requirements.
Outputs one of: ELIGIBLE | POSSIBLY ELIGIBLE | NOT ELIGIBLE | UNKNOWN.

Rule: eligibility is NEVER assumed when the source page does not provide the
information — the result is then UNKNOWN ("Unable to verify").
"""

import logging
from typing import Any, Dict, List

from app.graph import trace
from app.tools.eligibility_rules import evaluate_eligibility

logger = logging.getLogger(__name__)


def eligibility_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    profile = state.get("student_profile", {})
    opportunities = list(state.get("scraped_opportunities", []))

    checked = 0
    statuses: Dict[str, int] = {}

    for opp in opportunities:
        if "eligibility_status" in opp:  # already evaluated in an earlier round
            statuses[opp["eligibility_status"]] = statuses.get(opp["eligibility_status"], 0) + 1
            continue
        result = evaluate_eligibility(
            profile,
            opp.get("eligibility_details") or {},
            opp.get("eligibility") or "Not specified",
        )
        opp["eligibility_status"] = result["status"]
        opp["eligibility_reason"] = result["reason"]
        opp["eligibility_criteria"] = result["criteria"]
        checked += 1
        statuses[result["status"]] = statuses.get(result["status"], 0) + 1

    trace.record(
        "eligibility",
        f"checked {checked} opportunities ({len(opportunities) - checked} already checked)",
        **statuses,
    )
    logger.info("[Eligibility] %s", statuses)

    return {"eligible_opportunities": opportunities}
