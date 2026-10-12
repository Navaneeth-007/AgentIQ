"""Regression checks for evidence, date boundaries, and worker termination."""

import json

from app.agent.nodes import _prompt_evidence
from app.tools.python_repl import run_python_repl
from app.tools.sql_tool import complete_quarter


def test_quarter_ending_on_latest_date_is_complete():
    assert complete_quarter("2024-12-31") == {
        "start": "2024-10-01",
        "end": "2024-12-31",
    }
    assert complete_quarter("2024-12-30") == {
        "start": "2024-07-01",
        "end": "2024-09-30",
    }
    assert complete_quarter("2024-01-12") == {
        "start": "2023-10-01",
        "end": "2023-12-31",
    }


def test_large_sql_evidence_stays_valid_and_marks_preview():
    output = {
        "rows": [{"customer": "a" * 200, "revenue": i} for i in range(200)],
        "row_count": 200,
        "truncated": False,
    }
    parsed = json.loads(_prompt_evidence("sql_query", output))
    assert parsed["truncated"] is True
    assert len(parsed["rows"]) == 40
    assert len(output["rows"]) == 200


def test_python_receives_real_sql_rows_and_generates_chart():
    result = run_python_repl(
        "df = pd.DataFrame(sql_rows)\nprint(df['revenue'].sum())\n"
        "df.plot(x='region', y='revenue', kind='bar')\nplt.savefig(chart_path)",
        sql_rows=[
            {"region": "East", "revenue": 123.45},
            {"region": "West", "revenue": 10},
        ],
    )
    assert result["error"] is None
    assert "133.45" in result["stdout"]
    assert len(result["chart_paths"]) == 1


def test_python_timeout_terminates_worker(monkeypatch):
    import app.tools.python_repl as repl

    monkeypatch.setattr(repl, "EXECUTION_TIMEOUT_SECONDS", 2)
    result = repl.run_python_repl("while True: pass")
    assert "timed out" in result["error"]
    assert result["chart_paths"] == []
