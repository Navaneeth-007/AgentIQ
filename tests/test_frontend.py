"""Exercise automatic server authentication and a real demo in the UI."""

import json

import requests
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from app.config import ROOT
from app.demo import QUESTIONS
from app.main import app


def test_reviewer_opens_directly_and_downloads_demo(monkeypatch, tmp_path):
    import app.memory.long_term as memory

    monkeypatch.setattr(memory, "DB", tmp_path / "history.db")
    monkeypatch.setenv("AGENTIQ_API_TOKEN", "reviewer-code")
    with TestClient(app) as client:

        def adapt(method, url, **kwargs):
            path = "/" + url.split("/", 3)[3]
            res = client.request(
                method, path, headers=kwargs.get("headers"), json=kwargs.get("json")
            )
            response = requests.Response()
            response.status_code = res.status_code
            response._content = res.content
            response.headers.update(res.headers)
            return response

        monkeypatch.setattr(requests, "get", lambda url, **kw: adapt("GET", url, **kw))
        monkeypatch.setattr(
            requests, "post", lambda url, **kw: adapt("POST", url, **kw)
        )
        ui = AppTest.from_file(
            str(ROOT / "frontend" / "streamlit_app.py"), default_timeout=30
        ).run()
        assert not ui.exception
        assert not ui.text_input
        assert not ui.error
        ui.text_area[0].set_value(QUESTIONS[0]).run()
        next(b for b in ui.button if b.label == "Run analysis").click().run()
        assert not ui.exception
        assert len(ui.metric) == 3
        sid = ui.session_state["selected_run"]
        state = memory.get_run(sid)
        assert "data:image/png;base64" in state["report_html"]
        assert json.loads(
            client.get("/runs", headers={"Authorization": "Bearer reviewer-code"}).text
        )
