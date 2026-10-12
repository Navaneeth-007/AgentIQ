from app.reporting.evidence_report import evidence_report
from app.reporting.report_builder import build_html_report


def test_monthly_report_keeps_peak_value_bound_to_its_row():
    calls = [
        {
            "tool_name": "sql_query",
            "error": None,
            "tool_input": {"query": "SELECT month, region, revenue FROM source"},
            "tool_output": {
                "rows": [
                    {"month": "2023-02", "region": "West", "revenue": 5987.86},
                    {"month": "2024-11", "region": "East", "revenue": 6018.87},
                ]
            },
        }
    ]
    answer, markdown = evidence_report("monthly trends", calls, [])
    assert "2024-11" in answer and "East" in answer and "6,018.87" in answer
    html = build_html_report("monthly trends", markdown, [], calls, 0)
    assert "<td>2023-02</td>" in html and "<td>2024-11</td>" in html
    assert "<pre><code>" in html


def test_failed_analysis_never_claims_success():
    answer, report = evidence_report(
        "revenue", [{"tool_name": "sql_query", "error": "query failed"}], []
    )
    assert "incomplete" in answer
    assert "failed" in report


def test_missing_requested_chart_is_incomplete():
    answer, report = evidence_report("show a chart", [], [])
    assert "incomplete" in answer.lower()
    assert "not produced" in report
