"""
LangGraph node functions.

Each function takes AgentState and returns a partial state update (dict).
LangGraph merges the update into the existing state automatically.

Node flow:
  planner → executor → reflector → (executor | reporter)
                    ↑_______________|  (loop until done or max_retries)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.agent.state import AgentState, PlanStep, ToolCall
from app.agent.prompts import planner_prompt, executor_prompt, reflector_prompt, reporter_prompt
from app.generation.llm_client import LLMClient
from app.generation.cost_tracker import estimate_cost
from app.reporting.report_builder import build_html_report
from app.tools.sql_tool import run_sql_query
from app.tools.search_tool import run_web_search
from app.tools.python_repl import run_python_repl
from app.tools.file_tool import read_file
from app.tools.api_tool import fetch_api
from app.tools.email_tool import send_email

logger = logging.getLogger(__name__)

TOOL_REGISTRY = {
    "sql_query": run_sql_query,
    "web_search": run_web_search,
    "python_repl": run_python_repl,
    "file_read": read_file,
    "api_fetch": fetch_api,
    "email_send": send_email,
}


def _call_llm(client: LLMClient, prompt: str, state: AgentState) -> tuple[str, int, float]:
    """Call LLM, return (text, tokens_used, cost_usd)."""
    response = client.complete(prompt)
    tokens = response.get("usage", {}).get("total_tokens", 0)
    cost = estimate_cost(tokens, model=client.model)
    return response["content"], tokens, cost


def _parse_json(text: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON."""
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


# ── Node: Planner ─────────────────────────────────────────────────────────────

def planner_node(state: AgentState) -> dict:
    """
    Decompose the user's question into an ordered list of tool-use steps.
    On re-plan (retry), passes scratchpad so planner knows what's been tried.
    """
    client = LLMClient()
    prompt = planner_prompt(state["question"], scratchpad=state.get("scratchpad", ""))

    t0 = time.time()
    raw, tokens, cost = _call_llm(client, prompt, state)
    latency = (time.time() - t0) * 1000

    try:
        parsed = _parse_json(raw)
        steps: list[PlanStep] = [
            PlanStep(
                step_id=s["step_id"],
                description=s["description"],
                tool=s["tool"],
                status="pending",
            )
            for s in parsed["plan"]
        ]
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Planner JSON parse failed: %s\nRaw: %s", e, raw)
        steps = []

    logger.info("Plan created: %d steps", len(steps))

    return {
        "plan": steps,
        "current_step": 0,
        "total_tokens": state["total_tokens"] + tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
        "step_logs": state["step_logs"] + [{
            "node": "planner",
            "latency_ms": latency,
            "tokens": tokens,
        }],
    }


# ── Node: Executor ────────────────────────────────────────────────────────────

def executor_node(state: AgentState) -> dict:
    """
    Execute the current plan step.

    1. Ask LLM to determine exact tool input for this step.
    2. Call the tool.
    3. Append result to scratchpad.
    4. Advance current_step.
    """
    client = LLMClient()
    step_idx = state["current_step"]
    step = state["plan"][step_idx]

    logger.info("Executing step %d: %s (%s)", step_idx + 1, step["description"], step["tool"])

    # Ask LLM for exact tool input
    prompt = executor_prompt(step["description"], step["tool"], state["scratchpad"])
    t0 = time.time()
    raw, tokens, cost = _call_llm(client, prompt, state)
    latency = (time.time() - t0) * 1000

    tool_input: dict = {}
    tool_output: Any = None
    error: str | None = None

    try:
        tool_input = _parse_json(raw)
    except json.JSONDecodeError as e:
        error = f"Could not parse tool input: {e}"
        logger.error(error)

    # Execute the tool
    if not error:
        tool_fn = TOOL_REGISTRY.get(step["tool"])
        if tool_fn is None:
            error = f"Unknown tool: {step['tool']}"
        else:
            t1 = time.time()
            try:
                tool_output = tool_fn(**tool_input)
            except Exception as exc:
                error = str(exc)
                logger.error("Tool %s failed: %s", step["tool"], exc)
            latency += (time.time() - t1) * 1000

    # Build tool call record
    tool_call = ToolCall(
        tool_name=step["tool"],
        tool_input=tool_input,
        tool_output=tool_output,
        error=error,
        latency_ms=latency,
    )

    # Update plan step status
    updated_plan = list(state["plan"])
    updated_plan[step_idx] = {**step, "status": "failed" if error else "done"}

    # Append to scratchpad
    scratchpad_entry = (
        f"\n## Step {step_idx + 1}: {step['description']}\n"
        f"Tool: {step['tool']}\n"
        f"Output: {json.dumps(tool_output, default=str)[:2000]}\n"
        if not error else
        f"\n## Step {step_idx + 1}: {step['description']} [FAILED]\n"
        f"Error: {error}\n"
    )

    # Collect chart paths if python_repl generated them
    new_charts = []
    if step["tool"] == "python_repl" and isinstance(tool_output, dict):
        new_charts = tool_output.get("chart_paths", [])

    return {
        "plan": updated_plan,
        "current_step": step_idx + 1,
        "tool_calls": state["tool_calls"] + [tool_call],
        "scratchpad": state["scratchpad"] + scratchpad_entry,
        "chart_paths": state["chart_paths"] + new_charts,
        "total_tokens": state["total_tokens"] + tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
        "step_logs": state["step_logs"] + [{
            "node": "executor",
            "step": step_idx + 1,
            "tool": step["tool"],
            "latency_ms": latency,
            "tokens": tokens,
            "error": error,
        }],
    }


# ── Node: Reflector ───────────────────────────────────────────────────────────

def reflector_node(state: AgentState) -> dict:
    """
    Assess whether the current findings are sufficient to answer the question.
    Decides: continue with next step | replan | done.
    """
    client = LLMClient()
    prompt = reflector_prompt(
        state["question"],
        state["plan"],
        state["tool_calls"],
        state["scratchpad"],
    )

    t0 = time.time()
    raw, tokens, cost = _call_llm(client, prompt, state)
    latency = (time.time() - t0) * 1000

    try:
        parsed = _parse_json(raw)
        reflection = parsed.get("assessment", raw)
        next_action = parsed.get("next_action", "continue")
    except json.JSONDecodeError:
        reflection = raw
        next_action = "continue"

    retry_count = state["retry_count"]
    if next_action == "replan":
        retry_count += 1

    return {
        "reflection": reflection,
        "retry_count": retry_count,
        "total_tokens": state["total_tokens"] + tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
        "step_logs": state["step_logs"] + [{
            "node": "reflector",
            "next_action": next_action,
            "latency_ms": latency,
            "tokens": tokens,
        }],
    }


# ── Node: Reporter ────────────────────────────────────────────────────────────

def reporter_node(state: AgentState) -> dict:
    """
    Synthesise all findings into a structured markdown report and HTML version.
    """
    client = LLMClient()
    prompt = reporter_prompt(state["question"], state["scratchpad"], state["chart_paths"])

    t0 = time.time()
    raw, tokens, cost = _call_llm(client, prompt, state)
    latency = (time.time() - t0) * 1000

    report_markdown = raw
    report_html = build_html_report(
        question=state["question"],
        markdown_body=report_markdown,
        chart_paths=state["chart_paths"],
        tool_calls=state["tool_calls"],
        cost_usd=state["total_cost_usd"] + cost,
    )

    # Extract first paragraph as the one-line answer
    lines = [l.strip() for l in report_markdown.split("\n") if l.strip() and not l.startswith("#")]
    final_answer = lines[0] if lines else "Analysis complete. See full report."

    return {
        "report_markdown": report_markdown,
        "report_html": report_html,
        "final_answer": final_answer,
        "total_tokens": state["total_tokens"] + tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
        "step_logs": state["step_logs"] + [{
            "node": "reporter",
            "latency_ms": latency,
            "tokens": tokens,
        }],
    }


# ── Routing logic (used by graph.py) ─────────────────────────────────────────

def route_after_executor(state: AgentState) -> str:
    """After executing a step: go to reflector."""
    return "reflector"


def route_after_reflector(state: AgentState) -> str:
    """
    After reflection:
    - If retry limit hit → reporter (best effort)
    - If re-plan needed → planner
    - If more steps remain → executor
    - If all steps done → reporter
    """
    if state["retry_count"] >= state["max_retries"]:
        logger.warning("Max retries reached, forcing reporter.")
        return "reporter"

    # Check reflection result from last step log
    last_log = next(
        (l for l in reversed(state["step_logs"]) if l["node"] == "reflector"), {}
    )
    next_action = last_log.get("next_action", "continue")

    if next_action == "replan":
        return "planner"
    if next_action == "done" or state["current_step"] >= len(state["plan"]):
        return "reporter"
    return "executor"
