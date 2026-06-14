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
