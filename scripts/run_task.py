"""
CLI: run a single AgentIQ analysis task and print results.

Usage:
  python scripts/run_task.py --question "Which product category had the highest revenue?"
  python scripts/run_task.py --question "..." --save-report
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

# Make sure app/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.graph import run_agent


def main():
    parser = argparse.ArgumentParser(description="Run an AgentIQ analysis task.")
    parser.add_argument(
        "--question", required=True, help="Natural language question to analyse."
    )
    parser.add_argument(
        "--save-report", action="store_true", help="Save HTML report to data/reports/."
    )
    parser.add_argument("--json", action="store_true", help="Print full state as JSON.")
    args = parser.parse_args()

    session_id = str(uuid.uuid4())
    print(f"\n🔍 AgentIQ — session: {session_id[:8]}")
    print(f"   Question: {args.question}\n")

    state = run_agent(question=args.question, session_id=session_id)

    print("─" * 60)
    print(f"✅ Answer: {state['final_answer']}")
    print("\n📊 Stats:")
    print(f"   Tool calls:  {len(state['tool_calls'])}")
    print(f"   Tokens:      {state['total_tokens']:,}")
    print(f"   Est. cost:   ${state['total_cost_usd']:.4f}")
    print(f"   Retries:     {state['retry_count']}")

    if state["chart_paths"]:
        print("\n📈 Charts saved:")
        for p in state["chart_paths"]:
            print(f"   {p}")

    if args.save_report and state["report_html"]:
        out = Path("data/reports") / f"report_{session_id[:8]}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(state["report_html"])
        print(f"\n💾 HTML report saved to: {out}")

    if args.json:
        # Print full state minus the large HTML
        printable = {k: v for k, v in state.items() if k not in ("report_html",)}
        print("\n" + json.dumps(printable, indent=2, default=str))

    print()


if __name__ == "__main__":
    main()
