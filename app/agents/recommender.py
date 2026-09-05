import logging
from typing import Any, Dict, List
from app.config import settings
from app.database.models import Opportunity, StudentProfile
from app.graph.state import AgentState
from app.tools.match_calculator import calculate_match_score

logger = logging.getLogger(__name__)


def call_llm(prompt: str) -> str:
    """Invokes LLM prioritizing Google Gemini or Anthropic Claude."""
    # 1. Try Google Gemini
    if settings.gemini_api_key and settings.gemini_api_key != "your_gemini_api_key_here":
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            if response and response.text:
                logger.info("[Recommender Agent] Called Google Gemini API successfully.")
                return response.text
        except Exception as e:
            logger.warning(f"[Recommender Agent] Google Gemini call failed: {e}")

    # 2. Try Anthropic Claude
    if settings.anthropic_api_key and settings.anthropic_api_key != "your_anthropic_api_key_here":
        try:
            from langchain_anthropic import ChatAnthropic
            from langchain_core.messages import HumanMessage

            llm = ChatAnthropic(
                model="claude-3-5-sonnet-20241022",
                anthropic_api_key=settings.anthropic_api_key,
                temperature=0.3,
            )
            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content if isinstance(response.content, str) else str(response.content)
        except Exception as e:
            logger.warning(f"[Recommender Agent] Anthropic Claude call failed: {e}")

    return ""


def recommender_agent(state: AgentState) -> Dict[str, Any]:
    """Recommender Agent: Scores, ranks, and generates natural language explanations for opportunities."""
    raw_profile = state.get("student_profile", {})
    eligible_opps = state.get("eligible_opportunities", [])

    logger.info(f"[Recommender Agent] Scoring & ranking {len(eligible_opps)} opportunities.")

    try:
        student = StudentProfile(**raw_profile)
    except Exception as e:
        logger.error(f"[Recommender Agent] Error building StudentProfile model: {e}")
        student = None

    scored_list: List[Dict[str, Any]] = []

    for opp_dict in eligible_opps:
        opp_data = {k: v for k, v in opp_dict.items() if k not in ("is_eligible", "eligibility_reason")}
        try:
            opp_model = Opportunity(**opp_data)
            if student:
                score = calculate_match_score(student, opp_model)
            else:
                score = {"total_score": 0.0}
        except Exception as e:
            logger.warning(f"[Recommender Agent] Opportunity model parsing warning for '{opp_dict.get('title')}': {e}")
            score = {"total_score": 50.0}

        ranked_item = dict(opp_dict)
        ranked_item["match_score"] = score
        scored_list.append(ranked_item)

    # Sort descending by match score
    scored_list.sort(key=lambda x: x.get("match_score", {}).get("total_score", 0), reverse=True)

    final_output: List[Dict[str, Any]] = []

    for item in scored_list:
        title = item.get("title", "Opportunity")
        score_val = item.get("match_score", {}).get("total_score", 0)

        prompt = (
            f"Student Profile: Skills={raw_profile.get('skills')}, Interests={raw_profile.get('interests')}\n"
            f"Opportunity: {title} at {item.get('organization')}\n"
            f"Required Skills: {item.get('skills')}\n"
            f"Match Score: {score_val}%\n"
            f"Eligibility Status: {item.get('eligibility_reason')}\n\n"
            f"Write a concise 2-sentence explanation of why this opportunity matches the student and what key skill or requirement is missing or partial."
        )

        explanation = call_llm(prompt)
        if not explanation:
            explanation = f"Match score {score_val}%. Fits skills ({', '.join(item.get('skills', [])[:3])}) and profile criteria."

        item["fit_explanation"] = explanation.strip()
        final_output.append(item)

    logger.info(f"[Recommender Agent] Completed ranking. Outputting {len(final_output)} items.")

    return {
        "ranked_opportunities": scored_list,
        "final_output": final_output,
    }
