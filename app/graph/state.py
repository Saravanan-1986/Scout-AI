"""LangGraph agent state (spec section 15)."""

from typing import Any, Dict, List, TypedDict


class AgentState(TypedDict, total=False):
    # Input
    student_profile: Dict[str, Any]
    search_type: str  # "internship" | "hackathon" | "both"

    # Planning
    search_queries: List[str]
    used_queries: List[str]
    iteration: int

    # Research
    raw_search_results: List[Dict[str, Any]]
    processed_urls: List[str]
    scraped_opportunities: List[Dict[str, Any]]

    # Evaluation
    eligible_opportunities: List[Dict[str, Any]]
    ranked_opportunities: List[Dict[str, Any]]

    # Control / output
    quality: Dict[str, Any]
    final_output: List[Dict[str, Any]]
    agent_trace: List[Dict[str, Any]]
    errors: List[str]

