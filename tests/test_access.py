from fastapi.testclient import TestClient

from app.main import app


def test_shared_access_protects_data_and_documentation(monkeypatch):
    monkeypatch.setenv("AGENTIQ_API_TOKEN", "reviewer-code")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        for path in [
            "/runs",
            "/capabilities",
            "/trace/example",
            "/report/example",
            "/chart/example/0",
            "/docs",
            "/openapi.json",
        ]:
            assert client.get(path).status_code == 401
        assert client.post("/run", json={"question": "sales"}).status_code == 401
        assert (
            client.get(
                "/capabilities", headers={"Authorization": "Bearer reviewer-code"}
            ).json()["access_protected"]
            is True
        )


def test_feature_status_contains_no_credentials(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "secret-test-value")
    with TestClient(app) as client:
        response = client.get("/capabilities")
        assert response.status_code == 200
        assert "secret-test-value" not in response.text
