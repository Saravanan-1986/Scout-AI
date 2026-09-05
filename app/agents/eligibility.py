import logging
from typing import Any, Dict, List
from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def eligibility_agent(state: AgentState) -> Dict[str, Any]:
    """Eligibility Agent: Evaluates student criteria against candidate opportunities with full logging."""
    profile = state.get("student_profile", {})
    opportunities = state.get("scraped_opportunities", [])

    student_year = profile.get("year")
    student_cgpa = profile.get("cgpa", 0.0)
    student_dept = (profile.get("department") or "").lower()

    logger.info(f"[Eligibility Agent] Evaluating {len(opportunities)} opportunities for Student Year={student_year}, CGPA={student_cgpa}, Dept='{student_dept}'.")

    eligible_opportunities: List[Dict[str, Any]] = []

    for opp in opportunities:
        eligibility = opp.get("eligibility", {})
        req_years = eligibility.get("years", [])
        min_cgpa = eligibility.get("min_cgpa", 0.0)
        req_branches = [b.lower() for b in eligibility.get("branches", [])]

        reasons = []

        if req_years and student_year not in req_years:
            reasons.append(f"Year mismatch: Student year {student_year} not in required {req_years}")

        if student_cgpa < min_cgpa:
            reasons.append(f"CGPA mismatch: Student CGPA {student_cgpa} < required {min_cgpa}")

        if req_branches and student_dept not in req_branches:
            reasons.append(f"Branch mismatch: Student dept '{profile.get('department')}' not in required {req_branches}")

        opp_copy = dict(opp)
        title = opp.get("title", "Opportunity")

        if reasons:
            opp_copy["is_eligible"] = False
            opp_copy["eligibility_reason"] = "; ".join(reasons)
            logger.info(f"[Eligibility Agent] REJECTED '{title}': {opp_copy['eligibility_reason']}")
        else:
            opp_copy["is_eligible"] = True
            opp_copy["eligibility_reason"] = "Eligible"
            logger.info(f"[Eligibility Agent] PASSED '{title}'")

        eligible_opportunities.append(opp_copy)

    passed_count = sum(1 for o in eligible_opportunities if o.get("is_eligible"))
    logger.info(f"[Eligibility Agent] Summary: {passed_count}/{len(opportunities)} opportunities passed eligibility.")

    return {"eligible_opportunities": eligible_opportunities}
