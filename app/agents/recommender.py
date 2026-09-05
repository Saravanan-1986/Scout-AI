"""Recommendation Agent (Agent 5).

Ranks the scored opportunities and explains every recommendation using only
verified information (score breakdown + eligibility result). An LLM is used
when configured; otherwise a transparent rule-based explanation is generated.
"""

import logging
from typing import Any, Dict, List

from app.graph import trace
from app.graph.state import AgentState
from app.llm import call_llm, llm_available

logger = logging.getLogger(__name__)

_MAX_RESULTS = 10


def _rule_explanation(profile: Dict[str, Any], opp: Dict[str, Any]) -> str:
    """Build an explanation purely from the score breakdown + eligibility."""
    breakdown = (opp.get("match_score") or {}).get("breakdown", {})
    sentences: List[str] = []

    skill_note = breakdown.get("skill", {}).get("note", "")
    if skill_note:
        sentences.append(skill_note.rstrip("."))
    year_note = breakdown.get("year", {}).get("note", "")
    if year_note and "neutral" not in year_note.lower():
        sentences.append(year_note.rstrip("."))
    cgpa_note = breakdown.get("cgpa", {}).get("note", "")
    if cgpa_note and "neutral" not in cgpa_note.lower():
        sentences.append(cgpa_note.rstrip("."))
    location_note = breakdown.get("location", {}).get("note", "")
    if location_note and "neutral" not in location_note.lower():
        sentences.append(location_note.rstrip("."))

    if not sentences:
        sentences.append("The source page did not state detailed requirements, so alignment could not be verified.")

    explanation = ". ".join(sentences) + "."
    status = opp.get("eligibility_status", "UNKNOWN")
    if status == "UNKNOWN":
        explanation += " Eligibility: Unable to verify from the source page."
    return explanation


def _llm_explanation(profile: Dict[str, Any], opp: Dict[str, Any]) -> str:
    score = (opp.get("match_score") or {}).get("total", 0)
    prompt = (
        "You are the Recommendation Agent of ScoutAI. Explain in 2 concise sentences why this "
        "opportunity matches (or does not match) this student. Use ONLY the facts provided — "
        "never invent requirements, deadlines or benefits.\n\n"
        f"Student: {profile.get('degree', '')} {profile.get('department', '')}, year {profile.get('year', '')}, "
        f"CGPA {profile.get('cgpa', '')}; skills: {', '.join(profile.get('skills') or [])}; "
        f"interests: {', '.join(profile.get('interests') or [])}.\n"
        f"Opportunity: {opp.get('title')} by {opp.get('organization')} ({opp.get('type')})\n"
        f"Stated eligibility: {opp.get('eligibility', 'Not specified')[:300]}\n"
        f"Required skills: {', '.join(opp.get('required_skills') or []) or 'not specified'}\n"
        f"Match score: {score}/100. Eligibility status: {opp.get('eligibility_status')}\n"
        f"Score notes: "
        f"{'; '.join(str(v.get('note', '')) for v in (opp.get('match_score') or {}).get('breakdown', {}).values())}\n\n"
        "Explanation:"
    )
    return call_llm(prompt, temperature=0.3).strip()


def recommender_agent(state: AgentState) -> Dict[str, Any]:
    profile = state.get("student_profile", {})
    opportunities = list(state.get("eligible_opportunities", []))
    search_type = state.get("search_type", "both")

    # Rank by transparent match score.
    ranked = sorted(
        opportunities,
        key=lambda o: (o.get("match_score") or {}).get("total", 0),
        reverse=True,
    )[:_MAX_RESULTS]

    final_output: List[Dict[str, Any]] = []
    use_llm = llm_available()

    for rank, opp in enumerate(ranked, start=1):
        opp["rank"] = rank
        score = (opp.get("match_score") or {}).get("total", 0)
        explanation = ""
        if use_llm:
            try:
                explanation = _llm_explanation(profile, opp)
            except Exception as e:
                logger.warning("[Recommender] LLM explanation failed: %s", e)
        if not explanation:
            explanation = _rule_explanation(profile, opp)
        opp["fit_explanation"] = explanation
        final_output.append(opp)

    trace.record(
        "recommender",
        f"ranked top {len(final_output)} opportunities",
        top_pick=final_output[0]["title"] if final_output else None,
        top_score=(final_output[0].get("match_score") or {}).get("total") if final_output else None,
    )
    logger.info("[Recommender] Output %s ranked opportunities.", len(final_output))

    return {
        "ranked_opportunities": ranked,
        "final_output": final_output,
        "agent_trace": trace.get_trace(),
    }
