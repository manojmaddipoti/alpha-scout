"""Central model configuration for Alpha Scout.

Model availability changes often. Keep defaults narrow and override them with
environment variables when a provider releases or retires a model.
"""

from __future__ import annotations

import os

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro")

MODEL_CHOICES = [
    CLAUDE_MODEL,
    OPENAI_MODEL,
    GEMINI_MODEL,
]


def provider_for_model(model_name: str) -> str:
    """Resolve a configured model to its provider without ambiguous substrings."""
    normalized = model_name.strip().lower()
    configured = {
        CLAUDE_MODEL.lower(): "claude",
        OPENAI_MODEL.lower(): "openai",
        GEMINI_MODEL.lower(): "gemini",
    }
    if normalized in configured:
        return configured[normalized]
    if normalized.startswith("claude-"):
        return "claude"
    if normalized.startswith("gemini-"):
        return "gemini"
    if normalized.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    raise ValueError(f"Unsupported model: {model_name}")
