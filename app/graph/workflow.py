from langgraph.graph import END, START, StateGraph
from app.agents.eligibility import eligibility_agent
from app.agents.planner import planner_agent
from app.agents.recommender import recommender_agent
from app.agents.researcher import researcher_agent
from app.graph.state import AgentState


def create_scout_graph():
    """Builds and compiles the sequential LangGraph workflow for ScoutAI agents."""
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_agent)
    workflow.add_node("researcher", researcher_agent)
    workflow.add_node("eligibility", eligibility_agent)
    workflow.add_node("recommender", recommender_agent)

    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "eligibility")
    workflow.add_edge("eligibility", "recommender")
    workflow.add_edge("recommender", END)

    return workflow.compile()


scout_graph = create_scout_graph()
