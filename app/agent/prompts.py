"""
Prompt templates for every LangGraph node.

Design principle: prompts are explicit, versioned, and separated from logic.
Each node gets a dedicated function that formats its prompt from state.
"""

from __future__ import annotations

from app.capabilities import capabilities

AVAILABLE_TOOLS = """
Available tools:
  schema_inspect(db_path: str = "default")
    → Inspect available tables and columns in the database.
    → Use before writing SQL when the schema is not already known.

  sql_query(query: str, db_path: str = "default")
    → Execute a read-only SQL query. Returns rows as JSON.
    → Use for: structured data in the sample DB or any SQLite/Postgres source.

  web_search(query: str, num_results: int = 5)
    → Search the web for current information.
    → Use for: benchmarks, news, live metrics, anything not in the DB.

  python_repl(code: str)
    → Run Python code (pandas, matplotlib, numpy available).
    → Use for: aggregations, calculations, chart generation.
    → Charts saved to data/reports/ as PNG; paths returned in output.

  file_read(path: str)
    → Read CSV, JSON, or Parquet files. Returns a markdown table preview.
    → Use for: loading uploaded data files.

  api_fetch(service: str, params: dict)
    → Call external APIs. Supported services: weather, finance, news.
    → weather params: {"city": "Bengaluru", "days": 1} (1–5 days).
    → finance params: {"ticker": "IBM", "metric": "price"} (stock quotes only).
    → news params: {"query": "supply chain", "num_articles": 5}.
    → Use for: live data enrichment (e.g. weather for supply chain questions).

  email_send(to: str, subject: str, body: str, attachments: list[str] = [])
    → Send a report via email. `attachments` is a list of file paths.
    → Use only when the user explicitly asked for email delivery.
"""

DATA_RULES = """
For the bundled sample database:
- Revenue means SUM(orders.amount) for orders.status = 'delivered'. The amount is
  already the order total; do not multiply it by quantity.
- Sales periods use orders.order_date, not shipped_date, unless explicitly asked
  about shipping or delivery dates.
- Region means orders.region. Qualify column names when joining tables to avoid
  ambiguous columns; no customer join is needed to group sales by region.
- Customer lifetime value means delivered revenue observed in this dataset.
- Shipping delay is julianday(shipped_date) - julianday(order_date), for delivered
  orders with a non-null shipped_date. Do not use today's date for shipped orders.
- The data is synthetic historical data, not current business performance.
- Never aggregate a truncated row preview; compute aggregates in SQL.
- For rankings without a requested number of entries, return the top 10.
- For shipping summaries, query counts and regional aggregates in SQL rather
  than returning every order to summarize in the model.
- For "last quarter", use the latest_complete_quarter dates returned by
  schema_inspect exactly. If the latest date is a quarter's final day, that
  quarter IS complete and must be included (e.g. 2024-12-31 means Q4 2024).
"""


def planner_prompt(
    question: str, scratchpad: str = "", sample_data: bool = True
) -> str:
    context = f"\n\nContext from prior steps:\n{scratchpad}" if scratchpad else ""
    features = capabilities()
    availability = ", ".join(
        f"{name}={'enabled' if features[name] else 'unavailable'}"
        for name in ["web_search", "weather", "finance", "news", "email"]
    )
    return f"""You are a data analyst planning agent. Your job is to decompose the user's question into a precise, ordered list of steps to answer it fully.

{AVAILABLE_TOOLS}

{DATA_RULES if sample_data else "The selected source is an uploaded CSV in the uploaded_data table. Inspect its schema. Do not assume it has sample business columns or definitions."}

Optional feature availability: {availability}
Never plan unavailable features. If required, report that they need configuration.

Rules:
- Choose the minimum number of steps needed. Don't add steps for their own sake.
- Each step must specify exactly one tool.
- Use schema_inspect rather than inventing PRAGMA or sqlite_master queries when the schema is unknown.
- sql_query steps must include the intended SQL (or a description if schema_inspect runs first).
- For relative dates such as "last quarter", first establish the latest date represented by the data and use the latest complete quarter available in that data.
- python_repl steps for charts must describe what axes and data to plot.
- Only include email_send if the user explicitly asked to email results.
- Output ONLY valid JSON — no preamble, no explanation, no markdown fences.

Output format:
{{
  "plan": [
    {{"step_id": 1, "description": "...", "tool": "tool_name"}},
    ...
  ]
}}

User question: {question}{context}"""


def executor_prompt(
    step_description: str,
    tool_name: str,
    scratchpad: str,
    question: str = "",
    sample_data: bool = True,
) -> str:
    return f"""You are executing step: "{step_description}" using tool: {tool_name}.

Context from prior steps:
{scratchpad or "None yet."}

Original user question: {question}

{DATA_RULES if sample_data else "Use only columns found in the uploaded_data schema. The application supplies the selected database path automatically."}

{AVAILABLE_TOOLS}

Your task:
1. Determine the exact input to pass to {tool_name}.
2. Output ONLY valid JSON with the tool input. No preamble.

For sql_query: {{"query": "SELECT ...", "db_path": "default"}}
For schema_inspect: {{"db_path": "default"}}
For web_search: {{"query": "...", "num_results": 5}}
For python_repl: {{"code": "df = pd.DataFrame(...)\\nprint(df)"}}
Python already provides pd, np, plt, chart_path and sql_rows (the full rows from
the most recent successful SQL query). Build df = pd.DataFrame(sql_rows) rather
than retyping values or creating example data. Imports of pandas, numpy,
matplotlib, math, datetime, calendar, json, statistics, collections, itertools,
and decimal are supported; do not import other modules. Save charts
with plt.savefig(chart_path).
For file_read: {{"path": "..."}}
For api_fetch: {{"service": "weather|finance|news", "params": {{...}}}}
For email_send: {{"to": "...", "subject": "...", "body": "...", "attachments": []}}"""


def reflector_prompt(
    question: str, plan: list, tool_calls: list, scratchpad: str
) -> str:
    completed = [tc for tc in tool_calls if tc.get("error") is None]
    failed = [tc for tc in tool_calls if tc.get("error") is not None]

    return f"""You are a reflection agent reviewing the progress of a data analysis task.

Original question: {question}

Plan steps: {len(plan)} total
Completed tool calls: {len(completed)}
Failed tool calls: {len(failed)}
{f"Failures: {[f['error'] for f in failed]}" if failed else ""}

Current scratchpad:
{scratchpad or "Empty."}

Assess:
1. Is the question fully answerable from what we have? (yes/no)
2. If no, what is missing and what tool should we use next?
3. If there were failures, what should we retry differently?

Output ONLY valid JSON:
{{
  "complete": true | false,
  "assessment": "...",
  "next_action": "continue | replan | done",
  "replan_reason": "..." | null
}}"""


def reporter_prompt(question: str, scratchpad: str, chart_paths: list[str]) -> str:
    charts_note = (
        (
            "\n\nCharts generated (reference by filename):\n"
            + "\n".join(f"  - {p}" for p in chart_paths)
        )
        if chart_paths
        else ""
    )

    return f"""You are a senior data analyst writing a final report.

Original question: {question}

Analysis findings:
{scratchpad}
{charts_note}

Write a clear, structured analytical report in markdown. Include:
1. **Executive Summary** — 2-3 sentences answering the question directly.
2. **Findings** — Key data points, trends, and insights from the analysis.
3. **Data Sources** — Which tools / databases / APIs were used.
4. **Caveats** — Any limitations, data quality notes, or assumptions.

Rules:
- Write for a business stakeholder, not a data engineer.
- Be specific with numbers — don't say "high", say "42% above average".
- If charts were generated, reference them naturally in the findings.
- Do not invent data. Only report what was found in the analysis.
- Copy numerical results exactly from tool output. Never substitute example values.
- Compute derived totals, percentages, or averages with sql_query or python_repl before reporting them.
- If any required step failed or evidence is missing, explicitly say the analysis is incomplete.
- Write the report now using the evidence supplied. You cannot execute tools or
  run Python here. Do not emit tool calls; output markdown text only.
- Output markdown directly, no preamble."""
