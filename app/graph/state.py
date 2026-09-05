from typing import Any, Dict, List, TypedDict


class AgentState(TypedDict):
    student_profile: Dict[str, Any]
    search_queries: List[str]
    raw_search_results: List[Dict[str, Any]]
    scraped_opportunities: List[Dict[str, Any]]
    eligible_opportunities: List[Dict[str, Any]]
    ranked_opportunities: List[Dict[str, Any]]
    final_output: List[Dict[str, Any]]
