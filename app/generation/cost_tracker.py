"""Token cost estimation per model."""

from __future__ import annotations

# Cost per 1M tokens (input+output blended estimate), USD
COST_PER_1M_TOKENS: dict[str, float] = {
    "claude-sonnet-4-6": 3.00,
    "claude-opus-4-5": 15.00,
    "claude-haiku-4-5-20251001": 0.80,
    "gpt-4o": 5.00,
    "gpt-4o-mini": 0.15,
}

DEFAULT_COST = 3.00  # Fallback if model not in table


def estimate_cost(total_tokens: int, model: str = "claude-sonnet-4-6") -> float:
    """Return estimated USD cost for a given token count and model."""
    rate = COST_PER_1M_TOKENS.get(model, DEFAULT_COST)
    return round((total_tokens / 1_000_000) * rate, 6)
