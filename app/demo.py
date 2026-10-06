"""Credential-free showcase using real SQL results, not simulated answers."""

import time

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.agent.state import initial_state
from app.config import ROOT
from app.reporting.report_builder import build_html_report
from app.tools.sql_tool import inspect_schema, run_sql_query

QUESTIONS = [
    "Which product category had the highest revenue last quarter?",
    "Show me monthly sales trends for all regions as a chart.",
    "Which customers have the highest lifetime value?",
    "Find any orders with >7 day shipping delay and summarise them.",
]


def run_demo(question, session_id):
    if question not in QUESTIONS:
        raise ValueError(
            "Demo mode supports the four showcase questions. Select one or use Live AI mode."
        )
    state = initial_state(question, session_id)

    def tool(name, args, fn):
        start = time.perf_counter()
        result = fn(**args)
        state["tool_calls"].append(
            {
                "tool_name": name,
                "tool_input": args,
                "tool_output": result,
                "error": None,
                "latency_ms": (time.perf_counter() - start) * 1000,
            }
        )
        state["plan"].append(
            {
                "step_id": len(state["plan"]) + 1,
                "description": name.replace("_", " ").title(),
                "tool": name,
                "status": "done",
            }
        )
        return result

    tool("schema_inspect", {}, inspect_schema)
    dates = tool(
        "sql_query",
        {
            "query": "SELECT MIN(order_date) AS first_date, MAX(order_date) AS last_date FROM orders"
        },
        run_sql_query,
    )["rows"][0]
    if question == QUESTIONS[0]:
        latest = pd.Timestamp(dates["last_date"])
        quarter = latest.to_period("Q")
        if latest.date() < quarter.end_time.date():
            quarter -= 1
        start, end = str(quarter.start_time.date()), str(quarter.end_time.date())
        query = f"SELECT product_category, ROUND(SUM(amount),2) AS revenue FROM orders WHERE status='delivered' AND order_date BETWEEN '{start}' AND '{end}' GROUP BY product_category ORDER BY revenue DESC"
        title = f"Delivered revenue by category · {quarter}"
    elif question == QUESTIONS[1]:
        query = "SELECT substr(order_date,1,7) AS month, region, ROUND(SUM(amount),2) AS revenue FROM orders WHERE status='delivered' GROUP BY month, region ORDER BY month, region"
        title = "Monthly delivered sales by region"
    elif question == QUESTIONS[2]:
        query = "SELECT c.customer_id, c.name, ROUND(SUM(o.amount),2) AS revenue FROM customers c JOIN orders o ON c.customer_id=o.customer_id WHERE o.status='delivered' GROUP BY c.customer_id,c.name ORDER BY revenue DESC LIMIT 10"
        title = "Top customers by delivered revenue"
    else:
        query = "SELECT region, COUNT(*) AS delayed_orders, ROUND(AVG(julianday(shipped_date)-julianday(order_date)),1) AS average_delay_days FROM orders WHERE status='delivered' AND julianday(shipped_date)-julianday(order_date)>7 GROUP BY region ORDER BY delayed_orders DESC"
        title = "Delivered orders with shipping delays over seven days"
    result = tool("sql_query", {"query": query}, run_sql_query)
    df = pd.DataFrame(result["rows"])
    if df.empty:
        raise ValueError("No sample data found. Seed the database first.")
    start_time = time.perf_counter()
    fig, ax = plt.subplots(figsize=(10, 5))
    if question == QUESTIONS[1]:
        df.pivot(index="month", columns="region", values="revenue").plot(
            ax=ax, marker="o"
        )
        answer = f"Delivered sales total ${df.revenue.sum():,.2f} across {df.month.nunique()} months and {df.region.nunique()} regions."
    else:
        label, metric = (
            ("product_category", "revenue")
            if question == QUESTIONS[0]
            else (
                ("name", "revenue")
                if question == QUESTIONS[2]
                else ("region", "delayed_orders")
            )
        )
        df.plot.bar(x=label, y=metric, ax=ax, color="#6366f1", legend=False)
        answer = (
            f"{df.iloc[0][label]} leads with ${df.iloc[0][metric]:,.2f} in delivered revenue."
            if metric == "revenue"
            else f"{int(df.delayed_orders.sum())} delivered orders had shipping delays over seven days."
        )
    ax.set_title(title)
    ax.set_ylabel("Revenue (USD)" if question != QUESTIONS[3] else "Orders")
    fig.tight_layout()
    path = ROOT / "data" / "reports" / f"demo_{session_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    state["chart_paths"] = [str(path)]
    state["tool_calls"].append(
        {
            "tool_name": "chart_render",
            "tool_input": {"title": title},
            "tool_output": {"chart_paths": [str(path)]},
            "error": None,
            "latency_ms": (time.perf_counter() - start_time) * 1000,
        }
    )
    state["plan"].append(
        {
            "step_id": 4,
            "description": "Render analysis chart",
            "tool": "chart_render",
            "status": "done",
        }
    )
    state["current_step"] = 4
    state["final_answer"] = answer
    state["report_markdown"] = (
        f"## Executive Summary\n{answer}\n\n## Findings\n{df.to_markdown(index=False)}\n\n## Data Sources\nSeeded synthetic SQLite business data ({dates['first_date']} to {dates['last_date']}). Revenue includes delivered orders only.\n\n## Caveats\nCredential-free demo mode uses predefined analyses and real database calculations. Customer revenue covers the available dataset, not complete lifetime history. This is synthetic historical data, not current business performance."
    )
    state["step_logs"] = [
        {
            "node": "executor",
            "tool": tc["tool_name"],
            "latency_ms": tc["latency_ms"],
            "error": None,
        }
        for tc in state["tool_calls"]
    ]
    state["report_html"] = build_html_report(
        question, state["report_markdown"], state["chart_paths"], state["tool_calls"], 0
    )
    return state
