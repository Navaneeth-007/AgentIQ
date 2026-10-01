"""
AgentState — the single source of truth passed between every LangGraph node.

Design principle: all state is explicit and serialisable. Nothing is
stored in closures or global variables so the graph can be checkpointed,
replayed, and inspected at any node boundary.
"""

from __future__ import annotations

from typing import Any, Literal
from typing_extensions import TypedDict


class ToolCall(TypedDict):
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: Any
    error: str | None
    latency_ms: float


class PlanStep(TypedDict):
    step_id: int
    description: str
    tool: str
    status: Literal["pending", "running", "done", "failed"]


class AgentState(TypedDict):
    # ── Input ────────────────────────────────────────────────────────────────
    question: str                    # The user's natural-language question
    session_id: str                  # Unique session identifier

    # ── Plan ─────────────────────────────────────────────────────────────────
    plan: list[PlanStep]             # Ordered steps the planner decided on
    current_step: int                # Index into `plan`

    # ── Execution ────────────────────────────────────────────────────────────
    tool_calls: list[ToolCall]       # All tool invocations this run (for trace)
    scratchpad: str                  # Accumulated intermediate findings

    # ── Reflection ───────────────────────────────────────────────────────────
    reflection: str                  # Reflector node's latest assessment
    retry_count: int                 # How many times we've re-planned
    max_retries: int                 # Guard against infinite loops (default 3)

    # ── Output ───────────────────────────────────────────────────────────────
    report_markdown: str             # Final synthesised report (markdown)
    report_html: str                 # HTML version with inline charts
    chart_paths: list[str]           # Paths to generated chart images
    final_answer: str                # One-paragraph summary answer

    # ── Observability ────────────────────────────────────────────────────────
    total_tokens: int                # Cumulative token usage
    total_cost_usd: float            # Estimated cost
    step_logs: list[dict[str, Any]]  # Per-step timing + metadata


def initial_state(question: str, session_id: str) -> AgentState:
    """Return a clean initial state for a new agent run."""
    return AgentState(
        question=question,
        session_id=session_id,
        plan=[],
        current_step=0,
        tool_calls=[],
        scratchpad="",
        reflection="",
        retry_count=0,
        max_retries=3,
        report_markdown="",
        report_html="",
        chart_paths=[],
        final_answer="",
        total_tokens=0,
        total_cost_usd=0.0,
        step_logs=[],
    )
