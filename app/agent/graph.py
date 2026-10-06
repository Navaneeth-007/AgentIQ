"""
AgentIQ LangGraph state graph.

Graph topology:
  START → planner → executor → reflector → (planner | executor | reporter) → END

The reflector decides at each step whether to:
  - Continue to the next executor step
  - Re-plan from scratch (with scratchpad context)
  - Jump to reporter (analysis complete or max retries reached)
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agent.nodes import (
    executor_node,
    planner_node,
    reflector_node,
    reporter_node,
    route_after_reflector,
)
from app.agent.state import AgentState, initial_state


def build_graph() -> StateGraph:
    """Construct and compile the agent graph."""
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("reflector", reflector_node)
    graph.add_node("reporter", reporter_node)

    # Edges
    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "reflector")

    # Conditional routing from reflector
    graph.add_conditional_edges(
        "reflector",
        route_after_reflector,
        {
            "planner": "planner",
            "executor": "executor",
            "reporter": "reporter",
        },
    )

    graph.add_edge("reporter", END)

    return graph.compile()


# Singleton — compile once at import time
agent_graph = build_graph()


def run_agent(question: str, session_id: str) -> AgentState:
    """
    Run the agent on a question and return the final state.

    Args:
        question:   Natural-language question from the user.
        session_id: Unique session identifier for memory + logging.

    Returns:
        The final AgentState with report_markdown, report_html, and step_logs.
    """
    from app.guardrails import check_question

    check_question(question)
    state = initial_state(question=question, session_id=session_id)
    final_state: AgentState = agent_graph.invoke(state, config={"recursion_limit": 100})
    return final_state
