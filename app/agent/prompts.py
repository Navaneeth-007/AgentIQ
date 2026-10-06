"""
Prompt templates for every LangGraph node.

Design principle: prompts are explicit, versioned, and separated from logic.
Each node gets a dedicated function that formats its prompt from state.
"""

from __future__ import annotations

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
    → Use for: live data enrichment (e.g. weather for supply chain questions).

  email_send(to: str, subject: str, body: str, attachments: list[str] = [])
    → Send a report via email. `attachments` is a list of file paths.
    → Use only when the user explicitly asked for email delivery.
"""


def planner_prompt(question: str, scratchpad: str = "") -> str:
    context = f"\n\nContext from prior steps:\n{scratchpad}" if scratchpad else ""
    return f"""You are a data analyst planning agent. Your job is to decompose the user's question into a precise, ordered list of steps to answer it fully.

{AVAILABLE_TOOLS}

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


def executor_prompt(step_description: str, tool_name: str, scratchpad: str) -> str:
    return f"""You are executing step: "{step_description}" using tool: {tool_name}.

Context from prior steps:
{scratchpad or "None yet."}

{AVAILABLE_TOOLS}

Your task:
1. Determine the exact input to pass to {tool_name}.
2. Output ONLY valid JSON with the tool input. No preamble.

For sql_query: {{"query": "SELECT ...", "db_path": "default"}}
For schema_inspect: {{"db_path": "default"}}
For web_search: {{"query": "...", "num_results": 5}}
For python_repl: {{"code": "df = pd.DataFrame(...)\\nprint(df)"}}
Python already provides pd, np, plt and chart_path. Do not use imports. Save charts with plt.savefig(chart_path).
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
- Output markdown directly, no preamble."""
