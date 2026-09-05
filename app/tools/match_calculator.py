"""Match Calculator tool (spec TOOL 4) — transparent 0-100 scoring.

Weights (spec section 10):
    Skill match 40 | Education 20 | Year 15 | CGPA 10 | Interest 10 | Location 5

Honesty rule: when a component CANNOT be evaluated (the opportunity page does
not state it), it is scored NEUTRAL (half credit) and flagged "Unable to
verify" in the breakdown — never silently given full credit.
"""

from typing import Any, Dict, List

NEUTRAL_FACTOR = 0.5

WEIGHTS = {
    "skill": 40.0,
    "education": 20.0,
    "year": 15.0,
    "cgpa": 10.0,
    "interest": 10.0,
    "location": 5.0,
}


def _student_terms(profile: Dict[str, Any]) -> set:
    terms: set = set()
    for field in ("skills", "programming_languages", "technologies"):
        for item in profile.get(field) or []:
            low = str(item).lower().strip()
            if low:
                terms.add(low)
    return terms


def _component(score: float, max_score: float, note: str) -> Dict[str, Any]:
    return {"score": round(score, 2), "max": max_score, "note": note}


def _skill_component(profile: Dict[str, Any], opportunity: Dict[str, Any]) -> Dict[str, Any]:
    student_terms = _student_terms(profile)
    student_blob = " " + " ".join(student_terms) + " "
    opp_skills = sorted({str(s).lower().strip() for s in (opportunity.get("required_skills") or []) if str(s).strip()})
    if not opp_skills:
        return _component(
            WEIGHTS["skill"] * NEUTRAL_FACTOR,
            WEIGHTS["skill"],
            "The page does not list specific skills — scored neutral.",
        )
    matched = [
        skill for skill in opp_skills
        if skill in student_terms
        or any(term in skill or skill in term for term in student_terms)
        or skill in student_blob
    ]
    ratio = len(matched) / len(opp_skills)
    score = ratio * WEIGHTS["skill"]
    if matched:
        note = f"Your profile matches {len(matched)}/{len(opp_skills)} required skills ({', '.join(matched[:6])})."
    else:
        score = 0.0
        note = f"None of the mentioned skills ({', '.join(opp_skills[:6])}) match your profile."
    return _component(min(score, WEIGHTS["skill"]), WEIGHTS["skill"], note)
def _criterion_component(
    criterion: str,
    max_score: float,
    ok_note: str,
    conflict_note: str,
    unknown_note: str,
    criteria: Dict[str, str],
) -> Dict[str, Any]:
    state = criteria.get(criterion, "unknown")
    if state == "ok":
        return _component(max_score, max_score, ok_note)
    if state == "conflict":
        return _component(0.0, max_score, conflict_note)
    return _component(max_score * NEUTRAL_FACTOR, max_score, unknown_note)


def _interest_component(profile: Dict[str, Any], opportunity: Dict[str, Any]) -> Dict[str, Any]:
    interests = [str(i).lower().strip() for i in (profile.get("interests") or []) if str(i).strip()]
    opp_text = f"{opportunity.get('title', '')} {opportunity.get('description', '')}".lower()
    if not interests or len(opp_text) < 40:
        return _component(
            WEIGHTS["interest"] * NEUTRAL_FACTOR,
            WEIGHTS["interest"],
            "Interest alignment could not be evaluated — scored neutral.",
        )
    matched = [i for i in interests if i in opp_text]
    ratio = len(matched) / len(interests)
    note = (
        f"Matches your interests ({', '.join(matched)})."
        if matched
        else "The opportunity focuses on topics outside your listed interests."
    )
    return _component(ratio * WEIGHTS["interest"], WEIGHTS["interest"], note)


def _location_component(profile: Dict[str, Any], opportunity: Dict[str, Any]) -> Dict[str, Any]:
    opp_location = str(opportunity.get("location") or "").lower()
    preferred = [str(p).lower().strip() for p in (profile.get("preferred_locations") or []) if str(p).strip()]
    if not opp_location or opp_location == "not specified":
        return _component(
            WEIGHTS["location"] * NEUTRAL_FACTOR,
            WEIGHTS["location"],
            "The location is not stated on the page — scored neutral.",
        )
    if "remote" in opp_location or "online" in opp_location:
        if not preferred or any(p in ("remote", "any", "anywhere") for p in preferred):
            return _component(WEIGHTS["location"], WEIGHTS["location"], "Remote opportunity matches your preferences.")
        return _component(WEIGHTS["location"] * NEUTRAL_FACTOR, WEIGHTS["location"], "Remote, but you did not list remote as a preference.")
    for place in preferred:
        if place and place in opp_location:
            return _component(WEIGHTS["location"], WEIGHTS["location"], f"Located in your preferred area ({place.title()}).")
    return _component(0.0, WEIGHTS["location"], f"Located in {opp_location.title()}, outside your preferred locations.")


def calculate_match(profile: Dict[str, Any], opportunity: Dict[str, Any], eligibility_result: Dict[str, Any]) -> Dict[str, Any]:
    """Return {total, label, breakdown:{component:{score,max,note}}}."""
    criteria = eligibility_result.get("criteria", {})
    breakdown: Dict[str, Any] = {"skill": _skill_component(profile, opportunity)}

    breakdown["education"] = _criterion_component(
        "branch", WEIGHTS["education"],
        f"Your department ({profile.get('department', 'N/A')}) fits the opportunity's field.",
        "Your department does not match the requested field of study.",
        "The page does not clearly state a department requirement — scored neutral.",
        criteria,
    )
    breakdown["year"] = _criterion_component(
        "year", WEIGHTS["year"],
        f"The opportunity accepts students in year {profile.get('year', 'N/A')}.",
        "Your academic year does not meet the requirement.",
        "The required academic year is not stated — scored neutral.",
        criteria,
    )
    breakdown["cgpa"] = _criterion_component(
        "cgpa", WEIGHTS["cgpa"],
        f"Your CGPA ({profile.get('cgpa', 'N/A')}) meets the stated requirement.",
        "Your CGPA is below the stated requirement.",
        "No CGPA requirement was stated — scored neutral.",
        criteria,
    )
    breakdown["interest"] = _interest_component(profile, opportunity)
    breakdown["location"] = _location_component(profile, opportunity)

    total = round(sum(part["score"] for part in breakdown.values()), 2)
    return {"total": total, "label": _label_for(total), "breakdown": breakdown}


def _label_for(total: float) -> str:
    if total >= 85:
        return "Excellent Match"
    if total >= 70:
        return "Strong Match"
    if total >= 55:
        return "Good Match"
    if total >= 40:
        return "Moderate Match"
    return "Weak Match"


def match_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node: score every not-yet-scored opportunity transparently."""
    from app.graph import trace

    profile = state.get("student_profile", {})
    opportunities = list(state.get("eligible_opportunities", []))
    scored = 0
    for opp in opportunities:
        if "match_score" in opp:
            continue
        eligibility_result = {
            "status": opp.get("eligibility_status", "UNKNOWN"),
            "reason": opp.get("eligibility_reason", ""),
            "criteria": opp.get("eligibility_criteria") or {},
        }
        opp["match_score"] = calculate_match(profile, opp, eligibility_result)
        scored += 1

    trace.record("match_calculator", f"calculated match scores for {scored} opportunities")
    return {"eligible_opportunities": opportunities}



