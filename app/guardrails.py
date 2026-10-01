"""
Guardrails — applied before the agent loop runs.

Checks:
1. Input length and content validation
2. PII detection (emails, SSNs, credit card numbers)
3. Prompt injection detection
4. Tool call budget enforcement (prevent runaway agents)
"""

from __future__ import annotations

import re


MAX_QUESTION_LENGTH = 2000
MAX_TOOL_CALLS = 15  # Hard ceiling on tool calls per run


class GuardrailViolation(Exception):
    """Raised when a guardrail check fails."""
    pass


# ── Input checks ──────────────────────────────────────────────────────────────

def check_question(question: str) -> None:
    """Validate the user's question before starting the agent."""
    if not question or not question.strip():
        raise GuardrailViolation("Question cannot be empty.")

    if len(question) > MAX_QUESTION_LENGTH:
        raise GuardrailViolation(
            f"Question exceeds max length ({MAX_QUESTION_LENGTH} chars). "
            "Please be more concise."
        )

    check_prompt_injection(question)


def check_prompt_injection(text: str) -> None:
    """Detect common prompt injection patterns."""
    injection_patterns = [
        r"ignore (all |previous |prior )?instructions",
        r"disregard (all |your |the )?instructions",
        r"forget (everything|what you were told)",
        r"you are now",
        r"pretend (you are|to be)",
        r"act as (if|though|a)",
        r"new (role|persona|instructions):",
        r"system:?\s*you (are|must|should)",
        r"<\|.*?\|>",  # Token-level injection attempts
    ]
    lower = text.lower()
    for pattern in injection_patterns:
        if re.search(pattern, lower):
            raise GuardrailViolation(
                "Input contains patterns that look like a prompt injection attempt. "
                "Please rephrase your question."
            )


def check_pii(text: str) -> list[str]:
    """
    Detect potential PII in user input.
    Returns a list of PII type names found (empty = clean).

    Note: This is a heuristic check, not a complete PII scanner.
    """
    findings = []

    patterns = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
        "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    }

    for pii_type, pattern in patterns.items():
        if re.search(pattern, text):
            findings.append(pii_type)

    return findings


# ── Runtime checks ────────────────────────────────────────────────────────────

def check_tool_budget(tool_calls: list) -> None:
    """Raise if the agent has exceeded the max tool call budget."""
    if len(tool_calls) >= MAX_TOOL_CALLS:
        raise GuardrailViolation(
            f"Agent exceeded tool call budget ({MAX_TOOL_CALLS} calls). "
            "Stopping to prevent runaway execution."
        )


def check_sql_output(rows: list[dict]) -> None:
    """Warn if SQL results may contain PII columns."""
    pii_column_names = {"email", "ssn", "phone", "credit_card", "password", "dob", "date_of_birth"}
    columns = {str(k).lower() for row in rows[:1] for k in row.keys()}
    pii_found = columns & pii_column_names
    if pii_found:
        import logging
        logging.getLogger(__name__).warning(
            "SQL result contains potentially sensitive columns: %s", pii_found
        )
