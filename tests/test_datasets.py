import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tools.sql_tool import inspect_schema, run_sql_query


def test_csv_import_and_selection_use_real_database(monkeypatch, tmp_path):
    import app.main as api
    from app import datasets
    from app.agent.state import initial_state

    monkeypatch.setattr(datasets, "UPLOADS", tmp_path)
    selected = []

    def run(question, session_id, db_path):
        selected.append(db_path)
        state = initial_state(question, session_id, db_path)
        state["final_answer"] = "Test analysis"
        return state

    monkeypatch.setattr(api, "run_agent", run)
    import app.memory.long_term as memory

    monkeypatch.setattr(memory, "DB", tmp_path / "history.db")
    with TestClient(app) as client:
        uploaded = client.post(
            "/datasets?filename=sales.csv",
            content=b"region,revenue\nEast,123.45\nWest,10\n",
        )
        assert uploaded.status_code == 200
        data = uploaded.json()
        assert data["row_count"] == 2
        path = datasets.dataset_path(data["dataset_id"])
        assert inspect_schema(path)["tables"][0]["name"] == "uploaded_data"
        assert run_sql_query("SELECT SUM(revenue) AS revenue FROM uploaded_data", path)[
            "rows"
        ] == [{"revenue": 133.45}]
        response = client.post(
            "/run",
            json={
                "question": "What is the total revenue?",
                "dataset_id": data["dataset_id"],
            },
        )
        assert response.status_code == 200
        assert selected == [path]
        assert (
            client.post(
                "/run",
                json={
                    "question": "sales",
                    "mode": "demo",
                    "dataset_id": data["dataset_id"],
                },
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/run", json={"question": "sales", "dataset_id": "../../.env"}
            ).status_code
            == 400
        )


@pytest.mark.parametrize(
    "filename,content",
    [("bad.txt", b"a\n1"), ("empty.csv", b""), ("headers.csv", b"a,b\n")],
)
def test_invalid_uploads_rejected(filename, content, monkeypatch, tmp_path):
    from app import datasets

    monkeypatch.setattr(datasets, "UPLOADS", tmp_path)
    with TestClient(app) as client:
        assert (
            client.post(
                "/datasets", params={"filename": filename}, content=content
            ).status_code
            == 400
        )


def test_large_upload_rejected(monkeypatch):
    import app.main as api

    monkeypatch.setattr(api, "MAX_BYTES", 10)
    with TestClient(app) as client:
        assert (
            client.post("/datasets?filename=large.csv", content=b"x" * 11).status_code
            == 413
        )
