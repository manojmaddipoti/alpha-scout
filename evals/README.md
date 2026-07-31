# Evaluation set

`financial_research_questions.json` contains 25 hand-authored prompts covering
full underwriting, peer comparisons, SEC research, current events, financial
quality, safety, and edge cases.

Each case uses the canonical single-turn `EvaluationDataset` prompt shape and
adds project-specific `expected_tools` and `quality_criteria` fields. These
criteria are intended for rubric-based judging; they are deliberately not
asserted in unit tests because model output is nondeterministic.

The deterministic test suite validates the dataset's size, schema, unique IDs,
and category coverage:

```bash
pytest
```

Alpha Scout is a provider-neutral Streamlit agent rather than an ADK app, so an
inference adapter is still required before running the dataset with
`agents-cli eval generate`. The dataset itself can also be consumed by a custom
evaluation runner that calls `run_smart_agent`.
