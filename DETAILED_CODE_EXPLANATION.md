# Alpha Scout implementation guide

The current architecture and workflow are documented in [the independent research guide](docs/independent-research-guide.md) and [README](README.md).

The ticker pipeline is in `stock_research.py`; tool execution in `search_agent.py`; provenance in `research_evidence.py`; scenario math in `valuation.py`; user-isolated persistence in `database.py`. Personal portfolio context is not part of a research request.
