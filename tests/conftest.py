"""Keep developer access credentials out of ordinary API tests."""

import pytest


@pytest.fixture(autouse=True)
def local_test_access(monkeypatch):
    monkeypatch.delenv("AGENTIQ_API_TOKEN", raising=False)
