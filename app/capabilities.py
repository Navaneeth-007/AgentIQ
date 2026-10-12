"""Describe configured features without exposing provider credentials."""

import os


def enabled(name: str, configured: bool) -> bool:
    return configured and os.getenv(f"ENABLE_{name.upper()}", "true").lower() == "true"


def capabilities() -> dict:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    key_name = {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }.get(provider, "")
    return {
        "provider": provider,
        "live_ai": bool(os.getenv(key_name)),
        "database_analysis": True,
        "charts": True,
        "web_search": enabled(
            "web_search", bool(os.getenv("TAVILY_API_KEY") or os.getenv("SERPAPI_KEY"))
        ),
        "weather": enabled("weather", bool(os.getenv("OPENWEATHER_API_KEY"))),
        "finance": enabled("finance", bool(os.getenv("ALPHAVANTAGE_API_KEY"))),
        "news": enabled("news", bool(os.getenv("NEWSAPI_KEY"))),
        "email": enabled(
            "email", bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))
        ),
        "access_protected": bool(os.getenv("AGENTIQ_API_TOKEN")),
    }
