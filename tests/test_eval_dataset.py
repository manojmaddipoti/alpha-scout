import json
from pathlib import Path


def test_financial_research_eval_set_has_expected_coverage():
    dataset_path = (
        Path(__file__).parents[1] / "evals" / "financial_research_questions.json"
    )
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset["eval_cases"]

    assert 20 <= len(cases) <= 30
    assert len({case["eval_case_id"] for case in cases}) == len(cases)
    assert {case["category"] for case in cases} >= {
        "full_underwriting",
        "comparison",
        "sec_research",
        "current_events",
        "financial_quality",
        "safety",
        "edge_case",
    }
    for case in cases:
        assert case["prompt"]["role"] == "user"
        assert case["prompt"]["parts"][0]["text"].strip()
        assert case["expected_tools"]
        assert len(case["quality_criteria"]) >= 2
