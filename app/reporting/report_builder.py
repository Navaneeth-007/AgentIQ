"""
Report builder — converts markdown analysis into a self-contained HTML report
with inline base64 chart images.

Design: reports are single-file HTML (no external dependencies) so they can
be emailed, downloaded, or hosted as static files.
"""

from __future__ import annotations

import base64
from pathlib import Path


def _chart_to_base64(path: str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def build_html_report(
    question: str,
    markdown_body: str,
    chart_paths: list[str],
    tool_calls: list[dict],
    cost_usd: float,
) -> str:
    """
    Render a self-contained HTML analytical report.

    Args:
        question:      The original user question.
        markdown_body: The reporter node's markdown output.
        chart_paths:   Paths to generated chart PNGs.
        tool_calls:    List of tool call records (for the trace section).
        cost_usd:      Total estimated cost of the run.

    Returns:
        HTML string.
    """
    # Convert markdown to HTML (basic — headings, bold, paragraphs)
    body_html = _md_to_html(markdown_body)

    # Inline charts
    charts_html = ""
    for path in chart_paths:
        b64 = _chart_to_base64(path)
        if b64:
            name = Path(path).name
            charts_html += f"""
            <figure class="chart">
                <img src="data:image/png;base64,{b64}" alt="{name}" />
                <figcaption>{name}</figcaption>
            </figure>"""

    # Tool trace
    trace_rows = ""
    for i, tc in enumerate(tool_calls, 1):
        status = "✓" if tc.get("error") is None else "✗"
        trace_rows += f"""
        <tr>
            <td>{i}</td>
            <td>{tc.get('tool_name', '')}</td>
            <td class="{'ok' if tc.get('error') is None else 'err'}">{status}</td>
            <td>{round(tc.get('latency_ms', 0))}ms</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentIQ Report</title>
<style>
  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2a2d3a;
    --accent: #6366f1;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --ok: #22c55e;
    --err: #ef4444;
    --mono: "JetBrains Mono", "Fira Code", monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: "Inter", system-ui, sans-serif;
    font-size: 15px;
    line-height: 1.7;
  }}
  .header {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 2rem 3rem;
  }}
  .header h1 {{
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-size: 0.75rem;
    margin-bottom: 0.5rem;
  }}
  .header .question {{
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--text);
    max-width: 70ch;
  }}
  .meta {{
    margin-top: 0.75rem;
    font-size: 0.8rem;
    color: var(--muted);
  }}
  main {{ max-width: 800px; margin: 0 auto; padding: 2.5rem 3rem; }}
  h2 {{ font-size: 1.15rem; font-weight: 600; margin: 2rem 0 0.75rem; color: var(--text); }}
  h3 {{ font-size: 1rem; font-weight: 600; margin: 1.5rem 0 0.5rem; color: var(--text); }}
  p {{ margin-bottom: 1rem; color: var(--text); max-width: 70ch; }}
  strong {{ color: #fff; }}
  ul, ol {{ padding-left: 1.5rem; margin-bottom: 1rem; }}
  li {{ margin-bottom: 0.25rem; }}
  .chart {{ margin: 2rem 0; }}
  .chart img {{ width: 100%; border-radius: 8px; border: 1px solid var(--border); }}
  .chart figcaption {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.4rem; }}
  .trace {{
    margin-top: 3rem;
    border-top: 1px solid var(--border);
    padding-top: 2rem;
  }}
  .trace h2 {{ color: var(--muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.85rem; }}
  th {{ text-align: left; color: var(--muted); font-weight: 500; padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--border); }}
  td {{ padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--border); font-family: var(--mono); }}
  .ok {{ color: var(--ok); }}
  .err {{ color: var(--err); }}
  .cost {{ margin-top: 0.75rem; font-size: 0.8rem; color: var(--muted); }}
</style>
</head>
<body>
<div class="header">
  <h1>AgentIQ Report</h1>
  <div class="question">{question}</div>
  <div class="meta">{len(tool_calls)} tool calls · Est. cost: ${cost_usd:.4f}</div>
</div>
<main>
  {body_html}
  {charts_html}
  <div class="trace">
    <h2>Execution Trace</h2>
    <table>
      <thead><tr><th>#</th><th>Tool</th><th>Status</th><th>Latency</th></tr></thead>
      <tbody>{trace_rows}</tbody>
    </table>
    <div class="cost">Total estimated cost: ${cost_usd:.4f} USD</div>
  </div>
</main>
</body>
</html>"""


def _md_to_html(md: str) -> str:
    """Minimal markdown → HTML conversion (headings, bold, paragraphs)."""
    import re
    lines = md.split("\n")
    html_lines = []
    for line in lines:
        line = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
        if line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("# "):
            html_lines.append(f"<h2>{line[2:]}</h2>")
        elif line.startswith("- ") or line.startswith("* "):
            html_lines.append(f"<li>{line[2:]}</li>")
        elif line.strip() == "":
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p>{line}</p>")
    return "\n".join(html_lines)
