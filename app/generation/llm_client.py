"""
LLM client wrapper — Anthropic, OpenAI-compatible endpoints, or Groq.

Design principle: the agent nodes don't care which LLM they're calling.
All provider differences are contained here.
"""

from __future__ import annotations

import os
from typing import Any

from app import config  # noqa: F401


class LLMClient:
    """
    Thin wrapper around Anthropic / OpenAI / Groq completion APIs.

    Set LLM_PROVIDER=openai to switch. Default: anthropic.
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
        if self.provider not in {"anthropic", "openai", "groq"}:
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.provider}")
        self.model = self._default_model()

    def _default_model(self) -> str:
        if self.provider == "groq":
            return os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        if self.provider == "openai":
            return os.getenv("OPENAI_MODEL", "gpt-4o")
        return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        """
        Send a prompt and return {"content": str, "usage": {"total_tokens": N}}.
        """
        if self.provider in {"openai", "groq"}:
            return self._openai_complete(prompt, system, max_tokens, json_mode)
        return self._anthropic_complete(prompt, system, max_tokens)

    def _anthropic_complete(
        self, prompt: str, system: str | None, max_tokens: int
    ) -> dict:
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic not installed. Run: pip install anthropic")

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise OSError("ANTHROPIC_API_KEY not set in .env")

        client = anthropic.Anthropic(api_key=api_key)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        content = response.content[0].text if response.content else ""
        total_tokens = response.usage.input_tokens + response.usage.output_tokens

        return {"content": content, "usage": {"total_tokens": total_tokens}}

    def _openai_complete(
        self, prompt: str, system: str | None, max_tokens: int, json_mode: bool = False
    ) -> dict:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")

        key_name = "GROQ_API_KEY" if self.provider == "groq" else "OPENAI_API_KEY"
        api_key = os.getenv(key_name)
        if not api_key:
            raise OSError(f"{key_name} not set in .env")

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": float(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
        }
        base_url = (
            "https://api.groq.com/openai/v1"
            if self.provider == "groq"
            else os.getenv("OPENAI_BASE_URL")
        )
        if base_url:
            client_kwargs["base_url"] = base_url

        client = OpenAI(**client_kwargs)
        messages = [
            {
                "role": "system",
                "content": system
                or (
                    "You are a text-only data analyst. Tools are executed by the application, "
                    "never by you. Do not invoke Python, browser, or other built-in tools. "
                    "Return the requested JSON object or markdown text only. "
                    "Use exact values from the supplied evidence."
                ),
            }
        ]
        messages.append({"role": "user", "content": prompt})

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if json_mode:
            request_kwargs["response_format"] = {"type": "json_object"}
        if self.provider == "groq" and self.model.startswith("openai/gpt-oss-"):
            request_kwargs["reasoning_effort"] = "low"
        request_kwargs["temperature"] = 0.2
        if base_url and "openrouter.ai" in base_url:
            request_kwargs["extra_body"] = {"reasoning": {"exclude": True}}

        response = client.chat.completions.create(**request_kwargs)
        content = response.choices[0].message.content or ""
        if not content.strip():
            finish_reason = response.choices[0].finish_reason
            raise RuntimeError(
                "LLM returned no text content "
                f"(model={self.model}, finish_reason={finish_reason}). "
                "Try a non-reasoning model or increase the token limit."
            )
        total_tokens = response.usage.total_tokens if response.usage else 0

        return {"content": content, "usage": {"total_tokens": total_tokens}}
