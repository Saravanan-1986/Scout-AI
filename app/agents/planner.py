import logging
from typing import Any, Dict
from app.config import settings
from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def call_llm(prompt: str) -> str:
    """Invokes LLM prioritizing Google Gemini or Anthropic Claude."""
    api_key = settings.gemini_api_key
    if api_key and api_key != "your_gemini_api_key_here":
        # 1. Try google.genai (New SDK)
        try:
            from google import genai

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            if response and response.text:
                logger.info("[Planner Agent] Called Google GenAI API (gemini-2.5-flash) successfully.")
                return response.text
        except Exception as e1:
            logger.debug(f"[Planner Agent] google.genai attempt: {e1}")

        # 2. Try google.generativeai (Legacy SDK)
        try:
            import google.generativeai as legacy_genai

            legacy_genai.configure(api_key=api_key)
            model = legacy_genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            if response and response.text:
                logger.info("[Planner Agent] Called Google GenerativeAI API (gemini-1.5-flash) successfully.")
                return response.text
        except Exception as e2:
            logger.warning(f"[Planner Agent] Google Gemini call failed: {e2}")

    # 3. Try Anthropic Claude
    if settings.anthropic_api_key and settings.anthropic_api_key != "your_anthropic_api_key_here":
        try:
            from langchain_anthropic import ChatAnthropic
            from langchain_core.messages import HumanMessage

            llm = ChatAnthropic(
                model="claude-3-5-sonnet-20241022",
                anthropic_api_key=settings.anthropic_api_key,
                temperature=0.7,
            )
            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content if isinstance(response.content, str) else str(response.content)
        except Exception as e3:
            logger.warning(f"[Planner Agent] Anthropic Claude call failed: {e3}")

    return ""


def planner_agent(state: AgentState) -> Dict[str, Any]:
    """Planner Agent: Generates targeted search queries using Gemini/Claude or intelligent rules."""
    profile = state.get("student_profile", {})
    skills = profile.get("skills", [])
    interests = profile.get("interests", [])
    degree = profile.get("degree", "")
    department = profile.get("department", "")

    fallback_queries = [
        f"{skills[0] if skills else 'software'} internship 2026 {degree}",
        f"{interests[0] if interests else 'hackathon'} competition student 2026",
        f"{department} student internship tech hackathon",
    ]

    prompt = (
        f"You are a search planner for ScoutAI.\n"
        f"Student Profile:\n"
        f"- Degree: {degree}, Department: {department}\n"
        f"- Skills: {', '.join(skills)}\n"
        f"- Interests: {', '.join(interests)}\n\n"
        f"Generate 3 to 5 targeted search queries to find student internships and hackathons.\n"
        f"Output ONLY the query strings, one per line, without numbering or bullet points."
    )

    llm_output = call_llm(prompt)
    if llm_output:
        queries = [line.strip("- ").strip() for line in llm_output.strip().split("\n") if line.strip()]
        result_queries = queries[:5] if queries else fallback_queries
        logger.info(f"[Planner Agent] LLM generated queries: {result_queries}")
        return {"search_queries": result_queries}

    logger.info(f"[Planner Agent] Using profile-derived fallback queries: {fallback_queries}")
    return {"search_queries": fallback_queries}
