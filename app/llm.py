"""Centralized LLM access for every ScoutAI agent.

All LLM use is OPTIONAL: when no API key is configured every agent falls back
to transparent rule-based behaviour, so the terminal app always works.
"""

import json
import logging
import re
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_PLACEHOLDER_KEYS = {
    "",
    "your_gemini_api_key_here",
    "your_anthropic_api_key_here",
    "your_tavily_api_key_here",
}


def llm_available() -> bool:
    """True when at least one LLM provider key is configured and LLMs enabled."""
    if not settings.enable_llm:
        return False
    gemini_ok = settings.gemini_api_key not in _PLACEHOLDER_KEYS
    anthropic_ok = settings.anthropic_api_key not in _PLACEHOLDER_KEYS
    return gemini_ok or anthropic_ok


def call_llm(prompt: str, temperature: float = 0.2) -> str:
    """Invoke the configured LLM. Returns '' when unavailable or on failure.

    Priority: Google Gemini (new SDK -> legacy SDK) -> Anthropic Claude.
    """
    # 1. Google Gemini (new google-genai SDK)
    if settings.gemini_api_key not in _PLACEHOLDER_KEYS:
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config={"temperature": temperature},
            )
            if response and response.text:
                logger.info("[LLM] Gemini (%s) call succeeded.", settings.gemini_model)
                return response.text
        except Exception as e1:
            logger.debug("[LLM] google.genai attempt failed: %s", e1)

        # 2. Legacy google-generativeai SDK
        try:
            import google.generativeai as legacy_genai

            legacy_genai.configure(api_key=settings.gemini_api_key)
            model = legacy_genai.GenerativeModel(settings.gemini_model)
            response = model.generate_content(prompt)
            if response and response.text:
                logger.info("[LLM] Legacy Gemini call succeeded.")
                return response.text
        except Exception as e2:
            logger.warning("[LLM] Gemini call failed: %s", e2)

    # 3. Anthropic Claude
    if settings.anthropic_api_key not in _PLACEHOLDER_KEYS:
        try:
            from langchain_anthropic import ChatAnthropic
            from langchain_core.messages import HumanMessage

            llm = ChatAnthropic(
                model=settings.anthropic_model,
                anthropic_api_key=settings.anthropic_api_key,
                temperature=temperature,
            )
            response = llm.invoke([HumanMessage(content=prompt)])
            if response and response.content:
                logger.info("[LLM] Anthropic call succeeded.")
                return response.content if isinstance(response.content, str) else str(response.content)
        except Exception as e3:
            logger.warning("[LLM] Anthropic call failed: %s", e3)

    return ""


def extract_json(text: str) -> Optional[Any]:
    """Robustly pull the first JSON object/array out of an LLM response."""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        if start == -1:
            continue
        end = cleaned.rfind(closer)
        if end <= start:
            continue
        candidate = cleaned[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
