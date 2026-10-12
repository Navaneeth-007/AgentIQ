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
import os
import re
import time
from typing import Any

from app.agent.prompts import (
    executor_prompt,
    planner_prompt,
    reflector_prompt,
)
from app.agent.state import AgentState, PlanStep, ToolCall
from app.capabilities import capabilities
from app.errors import safe_error
from app.generation.cost_tracker import estimate_cost
from app.generation.llm_client import LLMClient
from app.guardrails import MAX_TOOL_CALLS, check_tool_budget
from app.reporting.evidence_report import evidence_report
from app.reporting.report_builder import build_html_report
from app.tools.api_tool import fetch_api
from app.tools.email_tool import send_email
from app.tools.file_tool import read_file
from app.tools.python_repl import run_python_repl
from app.tools.search_tool import run_web_search
from app.tools.sql_tool import inspect_schema, run_sql_query

logger = logging.getLogger(__name__)

TOOL_REGISTRY = {
    "schema_inspect": inspect_schema,
    "sql_query": run_sql_query,
    "web_search": run_web_search,
    "python_repl": run_python_repl,
    "file_read": read_file,
    "api_fetch": fetch_api,
    "email_send": send_email,
}


def _prompt_evidence(tool: str, output: Any) -> str:
    """Keep valid JSON evidence compact enough for a free model's token budget."""
    if tool == "schema_inspect" and isinstance(output, dict):
        output = {
            "tables": {
                t["name"]: {c["name"]: c["type"] for c in t["columns"]}
                for t in output.get("tables", [])
            },
            "date_context": output.get("date_context"),
        }
    encoded = json.dumps(output, default=str, separators=(",", ":"))
    if len(encoded) > 10000 and isinstance(output, dict) and "rows" in output:
        output = {
            **output,
            "rows": output["rows"][:40],
            "truncated": True,
            "note": "Prompt preview only. Use SQL aggregates; full output is in the trace.",
        }
        encoded = json.dumps(output, default=str, separators=(",", ":"))
    return encoded


def _call_llm(
    client: LLMClient,
    prompt: str,
    state: AgentState,
    *,
    json_mode: bool = False,
    max_tokens: int = 2048,
) -> tuple[str, int, float]:
    """Call LLM, return (text, tokens_used, cost_usd)."""
    response = client.complete(prompt, json_mode=json_mode, max_tokens=max_tokens)
    tokens = response.get("usage", {}).get("total_tokens", 0)
    cost = estimate_cost(tokens, model=client.model, provider=client.provider)
    return response["content"], tokens, cost


def _parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object even when a model adds fences or brief prose."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()

    decoder = json.JSONDecoder()
    last_error: json.JSONDecodeError | None = None
    for start in (index for index, char in enumerate(cleaned) if char == "{"):
        try:
            parsed, _ = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed

    if last_error:
        raise last_error
    raise json.JSONDecodeError("Expected a JSON object", cleaned, 0)


# ── Node: Planner ─────────────────────────────────────────────────────────────


def planner_node(state: AgentState) -> dict:
    """
    Decompose the user's question into an ordered list of tool-use steps.
    On re-plan (retry), passes scratchpad so planner knows what's been tried.
    """
    client = LLMClient()
    prompt = planner_prompt(
        state["question"],
        scratchpad=state.get("scratchpad", ""),
        sample_data=state.get("db_path", "default") == "default",
    )

    t0 = time.time()
    raw, tokens, cost = _call_llm(
        client, prompt, state, json_mode=True, max_tokens=1024
    )
    latency = (time.time() - t0) * 1000

    planner_error: str | None = None
    try:
        parsed = _parse_json(raw)
        plan_data = parsed.get("plan")
        if not isinstance(plan_data, list) or not plan_data:
            raise ValueError("Planner returned an empty or invalid plan")
        if any(
            not isinstance(s, dict) or s.get("tool") not in TOOL_REGISTRY
            for s in plan_data
        ):
            raise ValueError("Planner selected an unknown tool")
        steps: list[PlanStep] = [
            PlanStep(
                step_id=s["step_id"],
                description=s["description"],
                tool=s["tool"],
                status="pending",
            )
            for s in plan_data
        ]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.error("Planner JSON parse failed: %s\nRaw: %s", e, raw)
        planner_error = str(e)
        steps = [
            PlanStep(
                step_id=1,
                description="Inspect the available database tables and columns before planning the analysis.",
                tool="schema_inspect",
                status="pending",
            )
        ]

    logger.info("Plan created: %d steps", len(steps))

    return {
        "plan": steps,
        "current_step": 0,
        "total_tokens": state["total_tokens"] + tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
        "step_logs": state["step_logs"]
        + [
            {
                "node": "planner",
                "latency_ms": latency,
                "tokens": tokens,
                "error": planner_error,
            }
        ],
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
    check_tool_budget(state["tool_calls"])
    client = LLMClient()
    step_idx = state["current_step"]
    if step_idx >= len(state["plan"]):
        raise RuntimeError(
            f"Agent plan contains no executable step at index {step_idx}. "
            "The planner must return at least one valid step."
        )
    step = state["plan"][step_idx]

    logger.info(
        "Executing step %d: %s (%s)", step_idx + 1, step["description"], step["tool"]
    )

    # Ask LLM for exact tool input
    prompt = executor_prompt(
        step["description"],
        step["tool"],
        state["scratchpad"],
        state["question"],
        sample_data=state.get("db_path", "default") == "default",
    )
    t0 = time.time()
    if step["tool"] == "schema_inspect":
        raw, tokens, cost = '{"db_path": "default"}', 0, 0.0
    else:
        raw, tokens, cost = _call_llm(client, prompt, state, json_mode=True)
    latency = (time.time() - t0) * 1000

    tool_input: dict = {}
    tool_output: Any = None
    error: str | None = None

    try:
        tool_input = _parse_json(raw)
    except json.JSONDecodeError as e:
        error = f"Could not parse tool input: {e}"
        logger.error(error)

    # Some OpenRouter models wrap arguments in a tool-call-shaped object even
    # though this client requests plain JSON. Schema inspection has no model-
    # dependent inputs, so it can be recovered deterministically.
    if isinstance(tool_input.get("arguments"), dict):
        tool_input = tool_input["arguments"]
        error = None
    elif step["tool"] == "schema_inspect" and error:
        tool_input = {"db_path": "default"}
        error = None

    # Execute the tool
    if step["tool"] in {"schema_inspect", "sql_query"}:
        tool_input["db_path"] = state.get("db_path", "default")
    features = capabilities()
    feature = {"web_search": "web_search", "email_send": "email"}.get(step["tool"])
    if step["tool"] == "api_fetch":
        feature = tool_input.get("service")
    if feature and not features.get(feature, False):
        error = f"The {feature} feature is unavailable. Configure and enable it first."
    if not error:
        tool_fn = TOOL_REGISTRY.get(step["tool"])
        if tool_fn is None:
            error = f"Unknown tool: {step['tool']}"
        else:
            t1 = time.time()
            try:
                if step["tool"] == "python_repl":
                    last_sql = next(
                        (
                            tc
                            for tc in reversed(state["tool_calls"])
                            if tc["tool_name"] == "sql_query" and not tc.get("error")
                        ),
                        None,
                    )
                    tool_input["sql_rows"] = (
                        last_sql["tool_output"]["rows"] if last_sql else []
                    )
                tool_output = tool_fn(**tool_input)
                if isinstance(tool_output, dict) and tool_output.get("error"):
                    error = str(tool_output["error"])
            except Exception as exc:  # noqa: BLE001 — isolate tool failures
                error = safe_error(exc)
                logger.error("Tool %s failed: %s", step["tool"], error)
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
        f"Input: {json.dumps(tool_input, default=str) if step['tool'] != 'python_repl' else 'Analysis code is recorded in the trace.'}\n"
        f"Output: {_prompt_evidence(step['tool'], tool_output)}\n"
        if not error
        else f"\n## Step {step_idx + 1}: {step['description']} [FAILED]\n"
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
        "step_logs": state["step_logs"]
        + [
            {
                "node": "executor",
                "step": step_idx + 1,
                "tool": step["tool"],
                "latency_ms": latency,
                "tokens": tokens,
                "error": error,
            }
        ],
    }


# ── Node: Reflector ───────────────────────────────────────────────────────────


def reflector_node(state: AgentState) -> dict:
    """
    Assess whether the current findings are sufficient to answer the question.
    Decides: continue with next step | replan | done.
    """
    if os.getenv("LLM_REFLECTION", "false").lower() != "true":
        failed = bool(state["tool_calls"] and state["tool_calls"][-1].get("error"))
        more_steps = state["current_step"] < len(state["plan"])
        needs_chart = bool(
            re.search(
                r"\b(chart|plot|histogram|graph)\b", state["question"], re.IGNORECASE
            )
        )
        schema_only = all(
            tc["tool_name"] == "schema_inspect" for tc in state["tool_calls"]
        )
        if failed or (
            not more_steps
            and (schema_only or (needs_chart and not state["chart_paths"]))
        ):
            action = "replan"
            reflection = "The required evidence is missing or a tool failed; create a revised plan."
        else:
            action = "continue" if more_steps else "done"
            reflection = (
                "The tool succeeded; continue the remaining plan."
                if more_steps
                else "The planned tools completed."
            )
        return {
            "reflection": reflection,
            "retry_count": state["retry_count"] + (1 if action == "replan" else 0),
            "step_logs": state["step_logs"]
            + [
                {
                    "node": "reflector",
                    "next_action": action,
                    "latency_ms": 0,
                    "tokens": 0,
                }
            ],
        }
    client = LLMClient()
    prompt = reflector_prompt(
        state["question"],
        state["plan"],
        state["tool_calls"],
        state["scratchpad"],
    )

    t0 = time.time()
    raw, tokens, cost = _call_llm(client, prompt, state, json_mode=True, max_tokens=512)
    latency = (time.time() - t0) * 1000

    try:
        parsed = _parse_json(raw)
        reflection = parsed.get("assessment", raw)
        next_action = parsed.get("next_action", "continue")
    except json.JSONDecodeError:
        reflection = raw
        next_action = "continue"

    retry_count = state["retry_count"]
    if state["tool_calls"] and state["tool_calls"][-1].get("error"):
        next_action = "replan"
    needs_chart = bool(
        re.search(r"\b(chart|plot|histogram|graph)\b", state["question"], re.IGNORECASE)
    )
    if needs_chart and not state["chart_paths"] and next_action == "done":
        next_action = (
            "continue" if state["current_step"] < len(state["plan"]) else "replan"
        )
    if next_action == "replan":
        retry_count += 1

    return {
        "reflection": reflection,
        "retry_count": retry_count,
        "total_tokens": state["total_tokens"] + tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
        "step_logs": state["step_logs"]
        + [
            {
                "node": "reflector",
                "next_action": next_action,
                "latency_ms": latency,
                "tokens": tokens,
            }
        ],
    }


# ── Node: Reporter ────────────────────────────────────────────────────────────


def reporter_node(state: AgentState) -> dict:
    """
    Synthesise all findings into a structured markdown report and HTML version.
    """
    t0 = time.time()
    final_answer, report_markdown = evidence_report(
        state["question"],
        state["tool_calls"],
        state["chart_paths"],
        sample_data=state.get("db_path", "default") == "default",
    )
    tokens, cost = 0, 0.0
    latency = (time.time() - t0) * 1000
    report_html = build_html_report(
        question=state["question"],
        markdown_body=report_markdown,
        chart_paths=state["chart_paths"],
        tool_calls=state["tool_calls"],
        cost_usd=state["total_cost_usd"] + cost,
    )

    return {
        "report_markdown": report_markdown,
        "report_html": report_html,
        "final_answer": final_answer,
        "total_tokens": state["total_tokens"] + tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
        "step_logs": state["step_logs"]
        + [
            {
                "node": "reporter",
                "latency_ms": latency,
                "tokens": tokens,
            }
        ],
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
    if len(state["tool_calls"]) >= MAX_TOOL_CALLS:
        return "reporter"
    if state["retry_count"] >= state["max_retries"]:
        logger.warning("Max retries reached, forcing reporter.")
        return "reporter"

    # Tool failures need a fresh plan; continuing with a plan built on missing
    # data produces reports that look complete but contain no answer.
    if state["tool_calls"] and state["tool_calls"][-1].get("error"):
        return "planner"

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
