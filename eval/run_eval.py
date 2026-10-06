"""
AgentIQ evaluation harness.

Runs all golden tasks, scores them, and prints a summary table.
Paste the results into your README.

Usage:
  python eval/run_eval.py
  python eval/run_eval.py --tasks task_001,task_002   # subset
  python eval/run_eval.py --no-llm-grading            # skip LLM quality scoring
"""

from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

import argparse
import json
import logging
import time
from pathlib import Path

from app.agent.graph import run_agent
from app.generation.llm_client import LLMClient
from eval.metrics import (
    plan_efficiency,
    report_quality_llm,
    task_completion,
    tool_precision,
)

logging.basicConfig(level=logging.WARNING)

GOLDEN_TASKS_PATH = Path("eval/golden_tasks.json")


def run_eval(task_ids: list[str] | None = None, llm_grading: bool = True):
    with open(GOLDEN_TASKS_PATH) as f:
        tasks = json.load(f)

    if task_ids:
        tasks = [t for t in tasks if t["id"] in task_ids]

    if not tasks:
        raise ValueError("No matching evaluation tasks")
    llm_client = LLMClient() if llm_grading else None
    results = []

    print(f"\n{'=' * 70}")
    print(f"  AgentIQ Evaluation — {len(tasks)} tasks")
    print(f"{'=' * 70}\n")

    for task in tasks:
        tid = task["id"]
        question = task["question"]
        print(f"▶ {tid}: {question[:60]}...")

        t0 = time.time()
        try:
            state = run_agent(question=question, session_id=f"eval_{tid}")
            elapsed = time.time() - t0

            completion = task_completion(state)
            precision = tool_precision(state, task.get("expected_tools", []))
            efficiency = plan_efficiency(state, task.get("expected_min_steps", 1))
            quality = (
                report_quality_llm(question, state["report_markdown"], llm_client)
                if llm_grading and state["report_markdown"]
                else None
            )

            # Check answer contains expected keywords
            answer_lower = (
                state["final_answer"].lower() + state["report_markdown"].lower()
            )
            keyword_hit = all(
                kw.lower() in answer_lower for kw in task.get("answer_must_contain", [])
            )

            result = {
                "task_id": tid,
                "difficulty": task.get("difficulty", ""),
                "completion": completion,
                "tool_precision": round(precision, 2),
                "efficiency": round(efficiency, 2),
                "quality": round(quality, 2) if quality else "n/a",
                "keyword_hit": keyword_hit,
                "steps": len(state["tool_calls"]),
                "cost_usd": round(state["total_cost_usd"], 4),
                "latency_s": round(elapsed, 1),
                "status": "✅" if completion and keyword_hit else "❌",
            }
        except Exception as e:  # noqa: BLE001 — record evaluation failures
            result = {
                "task_id": tid,
                "difficulty": task.get("difficulty", ""),
                "status": "💥",
                "error": str(e),
                "completion": 0,
                "tool_precision": 0,
                "efficiency": 0,
                "quality": "n/a",
                "keyword_hit": False,
                "steps": 0,
                "cost_usd": 0,
                "latency_s": 0,
            }

        results.append(result)
        status = result["status"]
        steps = result.get("steps", "?")
        cost = result.get("cost_usd", 0)
        print(
            f"  {status}  steps={steps}  cost=${cost}  precision={result.get('tool_precision', '?')}"
        )

    # Summary
    completed = sum(1 for r in results if r["completion"] == 1.0)
    avg_precision = sum(r["tool_precision"] for r in results) / len(results)
    avg_efficiency = sum(r["efficiency"] for r in results) / len(results)
    avg_cost = sum(r["cost_usd"] for r in results) / len(results)
    total_cost = sum(r["cost_usd"] for r in results)

    quality_scores = [
        r["quality"] for r in results if isinstance(r.get("quality"), float)
    ]
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None

    print(f"\n{'=' * 70}")
    print(f"  RESULTS SUMMARY ({len(tasks)} tasks)")
    print(f"{'=' * 70}")
    print(
        f"  Task completion rate:   {completed}/{len(tasks)} ({completed / len(tasks) * 100:.0f}%)"
    )
    print(f"  Avg tool precision:     {avg_precision:.2f}")
    print(f"  Avg plan efficiency:    {avg_efficiency:.2f}")
    if avg_quality:
        print(f"  Avg report quality:     {avg_quality:.2f} / 1.0")
    print(f"  Avg cost per task:      ${avg_cost:.4f}")
    print(f"  Total eval cost:        ${total_cost:.4f}")
    print(f"{'=' * 70}\n")

    # Save results
    out_path = Path("eval/last_run_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Full results saved to: {out_path}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tasks", help="Comma-separated task IDs to run (default: all)"
    )
    parser.add_argument(
        "--no-llm-grading", action="store_true", help="Skip LLM quality grading"
    )
    args = parser.parse_args()

    task_ids = args.tasks.split(",") if args.tasks else None
    run_eval(task_ids=task_ids, llm_grading=not args.no_llm_grading)
