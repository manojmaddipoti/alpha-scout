import json

import search_agent


def test_dispatch_financial_metrics_normalizes_ticker(monkeypatch):
    monkeypatch.setattr(
        search_agent, "get_financial_metrics", lambda ticker: f"metrics:{ticker}"
    )
    found_tickers = []

    result = search_agent._dispatch_tool(
        "get_financial_metrics", {"ticker": " nvda "}, found_tickers
    )

    assert result == "metrics:NVDA"
    assert found_tickers == ["NVDA"]


def test_dispatch_competitors_tracks_normalized_unique_symbols(monkeypatch):
    monkeypatch.setattr(
        search_agent,
        "get_competitor_metrics",
        lambda target, peers: json.dumps({"target": target, "peers": peers}),
    )
    found_tickers = []

    result = search_agent._dispatch_tool(
        "get_competitor_metrics",
        {"target_ticker": "nvda", "competitors": ["amd", "avgo"]},
        found_tickers,
    )

    assert json.loads(result) == {"target": "NVDA", "peers": ["AMD", "AVGO"]}
    assert found_tickers == ["NVDA", "AMD", "AVGO"]


def test_web_search_limits_content_and_removes_raw_content(monkeypatch):
    class FakeTavily:
        def search(self, **kwargs):
            assert kwargs["topic"] == "news"
            assert kwargs["max_results"] == search_agent.WEB_SEARCH_MAX_RESULTS
            return {
                "results": [
                    {
                        "title": "Result",
                        "content": "x" * (search_agent.WEB_SEARCH_CONTENT_TRUNC + 20),
                        "raw_content": "large raw page",
                    }
                ]
            }

    monkeypatch.setattr(search_agent, "get_tavily_client", FakeTavily)

    payload = json.loads(search_agent.web_search("latest earnings"))
    result = payload["results"][0]
    assert len(result["content"]) == search_agent.WEB_SEARCH_CONTENT_TRUNC
    assert "raw_content" not in result


def test_unknown_tool_returns_explicit_error():
    assert (
        search_agent._dispatch_tool("missing_tool", {}, [])
        == "Unknown tool: missing_tool"
    )
