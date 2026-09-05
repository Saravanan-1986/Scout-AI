"""LangGraph workflow for the ScoutAI agentic pipeline (spec section 15).

    START → planner → researcher → eligibility → match → quality_evaluator
                          ↑                                   │
                          └────────── (replan) ←──────────────┘
                                                              │ (finish)
                                                              ↓
                                                        recommender → END

The quality evaluator loops back to the planner when not enough verified
relevant opportunities were found (bounded by ``settings.max_iterations``).
"""

from langgraph.graph import END, START, StateGraph

from app.agents.eligibility import eligibility_agent
from app.agents.planner import planner_agent
from app.agents.quality_evaluator import quality_evaluator_agent, route_after_quality
from app.agents.recommender import recommender_agent
from app.agents.researcher import researcher_agent
from app.graph.state import AgentState
from app.tools.match_calculator import match_agent


def create_scout_graph():
    """Builds and compiles the ScoutAI multi-agent workflow."""
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_agent)
    workflow.add_node("researcher", researcher_agent)
    workflow.add_node("eligibility", eligibility_agent)
    workflow.add_node("match", match_agent)
    workflow.add_node("quality_evaluator", quality_evaluator_agent)
    workflow.add_node("recommender", recommender_agent)

    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "eligibility")
    workflow.add_edge("eligibility", "match")
    workflow.add_edge("match", "quality_evaluator")
    workflow.add_conditional_edges(
        "quality_evaluator",
        route_after_quality,
        {"replan": "planner", "finish": "recommender"},
    )
    workflow.add_edge("recommender", END)

    return workflow.compile()


scout_graph = create_scout_graph()

