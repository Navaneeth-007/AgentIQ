"""Exercise the real demo, persistence, downloads, and retry bounds."""

from fastapi.testclient import TestClient

from app.agent.nodes import route_after_reflector
from app.agent.state import initial_state
from app.demo import QUESTIONS
from app.guardrails import MAX_TOOL_CALLS
from app.main import app


def test_showcase_end_to_end(tmp_path, monkeypatch):
    import app.memory.long_term as memory

    monkeypatch.setattr(memory, "DB", tmp_path / "history.db")
    with TestClient(app) as client:
        for question in QUESTIONS:
            response = client.post("/run", json={"question": question, "mode": "demo"})
            assert response.status_code == 200, response.text
            data = response.json()
            sid = data["session_id"]
            assert data["step_count"] == 4
            assert data["total_tokens"] == 0
            trace = client.get(f"/trace/{sid}").json()
            assert trace["chart_count"] == 1
            assert "synthetic" in trace["report_markdown"]
            report = client.get(f"/report/{sid}")
            assert report.headers["content-type"].startswith("text/html")
            assert "data:image/png;base64" in report.text
            chart = client.get(f"/chart/{sid}/0")
            assert chart.content.startswith(b"\x89PNG")
            assert client.get(f"/chart/{sid}/-1").status_code == 404
        assert len(client.get("/runs").json()) == 4
        assert (
            client.post(
                "/run", json={"question": "unsupported", "mode": "demo"}
            ).status_code
            == 400
        )
        assert (
            client.post("/run", json={"question": "", "mode": "demo"}).status_code
            == 400
        )


def test_old_failure_does_not_force_replanning():
    state = initial_state("sales", "test")
    state["tool_calls"] = [{"error": "old failure"}, {"error": None}]
    state["plan"] = [{"status": "done"}, {"status": "pending"}]
    state["current_step"] = 1
    assert route_after_reflector(state) == "executor"
    state["tool_calls"] = [{"error": None}] * MAX_TOOL_CALLS
    assert route_after_reflector(state) == "reporter"


def test_report_escapes_untrusted_text():
    from app.reporting.report_builder import build_html_report

    report = build_html_report(
        "<script>alert(1)</script>", "<img src=x onerror=alert(1)>", [], [], 0
    )
    assert "<script>" not in report
    assert "<img src=x" not in report
