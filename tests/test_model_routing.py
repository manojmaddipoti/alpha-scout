import pytest

import search_agent
from model_config import (
    CLAUDE_MODEL,
    GEMINI_MODEL,
    OPENAI_MODEL,
    provider_for_model,
)


@pytest.mark.parametrize(
    ("model_name", "expected_provider"),
    [
        (CLAUDE_MODEL, "claude"),
        (OPENAI_MODEL, "openai"),
        (GEMINI_MODEL, "gemini"),
        ("claude-sonnet-custom", "claude"),
        ("gpt-custom", "openai"),
        ("o3-mini", "openai"),
        ("gemini-custom", "gemini"),
    ],
)
def test_provider_for_model(model_name, expected_provider):
    assert provider_for_model(model_name) == expected_provider


def test_provider_for_model_rejects_unknown_model():
    with pytest.raises(ValueError, match="Unsupported model"):
        provider_for_model("mystery-model")


@pytest.mark.parametrize(
    ("model_name", "function_name"),
    [
        (CLAUDE_MODEL, "run_claude_logic"),
        (OPENAI_MODEL, "run_openai_logic"),
        (GEMINI_MODEL, "run_gemini_logic"),
    ],
)
def test_run_smart_agent_routes_to_selected_provider(
    monkeypatch, model_name, function_name
):
    expected = (f"{function_name} response", ["TEST"])

    def fake_runner(messages, selected_model):
        assert messages == [{"role": "user", "content": "Analyze TEST"}]
        assert selected_model == model_name
        return expected

    monkeypatch.setattr(search_agent, function_name, fake_runner)

    assert search_agent.run_smart_agent(
        [{"role": "user", "content": "Analyze TEST"}], model_name
    ) == expected
