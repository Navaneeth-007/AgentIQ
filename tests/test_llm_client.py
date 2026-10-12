"""Verify provider isolation without making billable network requests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.generation.cost_tracker import estimate_cost
from app.generation.llm_client import LLMClient


def test_groq_uses_own_key_model_and_endpoint(monkeypatch):
    import openai

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "other-provider-key")
    sdk = MagicMock()
    sdk.return_value.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))],
        usage=SimpleNamespace(total_tokens=20),
    )
    monkeypatch.setattr(openai, "OpenAI", sdk)
    client = LLMClient()
    assert client.complete("test")["content"] == "OK"
    assert sdk.call_args.kwargs["api_key"] == "test-groq-key"
    assert sdk.call_args.kwargs["base_url"] == "https://api.groq.com/openai/v1"
    request = sdk.return_value.chat.completions.create.call_args.kwargs
    assert request["model"] == "openai/gpt-oss-120b"
    assert "extra_body" not in request


def test_groq_does_not_fall_back_to_openai_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "other-provider-key")
    with pytest.raises(OSError, match="GROQ_API_KEY"):
        LLMClient().complete("test")


def test_free_cost_setting_is_provider_specific(monkeypatch):
    monkeypatch.setenv("GROQ_FREE_TIER", "true")
    assert estimate_cost(1000, "openai/gpt-oss-120b", "groq") == 0
    assert estimate_cost(1000, "gpt-4o", "openai") > 0


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "typo")
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        LLMClient()
