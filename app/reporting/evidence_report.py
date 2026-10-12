"""Build database reports directly from execution evidence, without invented facts."""

import json


def _value(value, currency=False):
    if isinstance(value, float):
        return f"${value:,.2f}" if currency else f"{value:,.2f}"
    return str(value) if value is not None else "No value"


def _table(rows: list[dict], limit=40) -> str:
    if not rows:
        return "No matching rows."
    columns = list(rows[0])

    def cell(value):
        return _value(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines.extend(
        "| " + " | ".join(cell(row.get(col)) for col in columns) + " |"
        for row in rows[:limit]
    )
    if len(rows) > limit:
        lines.append(
            f"\nShowing {limit} of {len(rows)} returned rows; full results are in Execution evidence."
        )
    return "\n".join(lines)


def evidence_report(
    question: str,
    tool_calls: list[dict],
    chart_paths: list[str],
    sample_data: bool = True,
) -> tuple[str, str]:
    successful = [tc for tc in tool_calls if not tc.get("error")]
    sql = [tc for tc in successful if tc["tool_name"] == "sql_query"]
    failures = [tc for tc in tool_calls if tc.get("error")]
    answer = "Analysis complete. The findings below contain the recorded tool results."
    if sql:
        rows = sql[-1]["tool_output"]["rows"]
        if rows and all(k in rows[0] for k in ("month", "region", "revenue")):
            peak = max(rows, key=lambda row: row["revenue"] or 0)
            answer = (
                f"The highest returned monthly revenue was {_value(float(peak['revenue']), sample_data)} "
                f"for {peak['region']} in {peak['month']}."
            )
        elif rows:
            facts = "; ".join(
                f"{key.replace('_', ' ').title()}: "
                f"{_value(value, sample_data and any(s in key.lower() for s in ('revenue', 'amount', 'value')))}"
                for key, value in rows[0].items()
            )
            answer = (
                (
                    "Top result — "
                    if len(rows) > 1
                    and "ORDER BY" in sql[-1]["tool_input"]["query"].upper()
                    else "Result — "
                )
                + facts
                + "."
            )
        else:
            answer = "No rows matched the analysis query."
    elif not successful or all(
        tc["tool_name"] == "schema_inspect" for tc in successful
    ):
        answer = "The analysis is incomplete: no analysis results were produced."

    needs_chart = any(
        word in question.lower().split() for word in ("chart", "plot", "histogram")
    )
    if (tool_calls and tool_calls[-1].get("error")) or (
        needs_chart and not chart_paths
    ):
        answer = "Analysis incomplete. Available result: " + answer
    sections = [f"## Executive Summary\n{answer}", "## Findings"]
    for index, tc in enumerate(sql, 1):
        output = tc["tool_output"]
        sections.append(f"### Query {index}\n{_table(output['rows'])}")
        if output.get("truncated"):
            sections.append(
                "This query reached the row limit. These results are partial; totals over this preview are not complete."
            )
        sections.append(f"SQL used:\n```sql\n{tc['tool_input']['query']}\n```")
    for tc in successful:
        output = tc.get("tool_output") or {}
        if tc["tool_name"] == "python_repl" and output.get("stdout", "").strip():
            sections.append(
                f"### Calculation output\n```text\n{output['stdout'].strip()}\n```"
            )
        elif tc["tool_name"] not in {"schema_inspect", "sql_query", "python_repl"}:
            sections.append(
                f"### {tc['tool_name'].replace('_', ' ').title()}\n```json\n{json.dumps(output, indent=2, default=str)}\n```"
            )
    if chart_paths:
        sections.append(
            f"### Charts\n{len(chart_paths)} chart(s) generated from the recorded analysis data and included in the downloadable report."
        )
    sources = ", ".join(dict.fromkeys(tc["tool_name"] for tc in successful)) or "None"
    sections.append(
        f"## Data Sources\n{sources}. Full tool inputs and outputs are available under Execution evidence."
    )
    caveats = [
        "This report copies recorded results directly; query definitions still need to match your business question."
    ]
    if sample_data:
        caveats.append(
            "The bundled data is synthetic historical data. Revenue is delivered order revenue; customer value covers the observed dataset."
        )
    if failures:
        caveats.append(
            f"{len(failures)} earlier tool call(s) failed. Review the trace to confirm the subsequent steps recovered the required evidence."
        )
    if not chart_paths and needs_chart:
        caveats.append(
            "The requested chart was not produced; this analysis is incomplete."
        )
    sections.append("## Caveats\n" + "\n".join(f"- {item}" for item in caveats))
    return answer, "\n\n".join(sections)
