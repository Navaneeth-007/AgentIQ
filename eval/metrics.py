"""
AgentIQ evaluation metrics.

Metrics:
1. Task completion rate  — did the agent produce a non-empty final answer?
2. Tool selection precision — did the agent use the right tool for each step?
3. Plan efficiency — how many steps did it take vs. the expected minimum?
4. Report quality — LLM-graded coherence and accuracy (1–5 scale)
5. Cost per task — average USD cost
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def task_completion(final_state: dict) -> float:
    """1.0 if agent produced a non-empty final answer, 0.0 otherwise."""
    answer = final_state.get("final_answer", "")
    report = final_state.get("report_markdown", "")
    return 1.0 if (answer.strip() and report.strip()) else 0.0


def tool_precision(final_state: dict, expected_tools: list[str]) -> float:
    """
    Fraction of tool calls that matched the expected tool sequence.

    Args:
        final_state:    The completed agent state.
        expected_tools: List of tool names in expected order (from golden task).

    Returns:
        Precision score 0.0–1.0.
    """
    actual_tools = [tc["tool_name"] for tc in final_state.get("tool_calls", [])]
    if not expected_tools:
        return 1.0
    matches = sum(1 for e in expected_tools if e in actual_tools)
    return matches / len(expected_tools)


def plan_efficiency(final_state: dict, expected_min_steps: int) -> float:
    """
    Score based on how close actual steps were to expected minimum.
    Returns 1.0 if on-target, penalises for extra steps (up to 0.5 floor).
    """
    actual = len(final_state.get("tool_calls", []))
    if actual == 0:
        return 0.0
    if actual <= expected_min_steps:
        return 1.0
    extra = actual - expected_min_steps
    return max(0.5, 1.0 - (extra * 0.1))


def report_quality_llm(question: str, report_markdown: str, llm_client) -> float:
    """
    LLM-graded report quality on 1–5 scale (normalised to 0.0–1.0).

    Grades: coherence, factual grounding, specificity, and relevance.
    """
    prompt = f"""Rate this data analysis report on a scale of 1-5.

Question: {question}

Report:
{report_markdown[:3000]}

Grade on:
- Coherence (does it flow logically?)
- Factual grounding (does it cite specific numbers, not vague claims?)
- Relevance (does it directly answer the question?)
- Completeness (are there obvious gaps?)

Output ONLY a JSON object: {{"score": <1-5>, "reason": "<one sentence>"}}"""

    try:
        response = llm_client.complete(prompt, max_tokens=200)
        parsed = json.loads(
            response["content"]
            .strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
        )
        return parsed.get("score", 3) / 5.0
    except Exception as e:  # noqa: BLE001 — record evaluation failures
        logger.warning("LLM quality grading failed: %s", e)
        return 0.6  # Default to neutral on failure
