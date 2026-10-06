# Alpha Scout Independent Equity Research

Enter a ticker to get a standalone investigation of the company and its stock:
business economics, financial history, earnings quality, competitors, valuation,
catalysts, risks and a supported research verdict. **No portfolio information is
required or used.** Personal portfolio monitoring and recommendations belong to
the separate [alpha-scout-research](https://github.com/manojmaddipoti/alpha-scout-research) project.

## What a ticker report contains

1. Research verdict, issuer identity, price date, currency, horizon and confidence.
2. Business model, industry economics and competitive advantage.
3. Historical financial statements and forensic accounting.
4. Balance sheet, funding risk, dilution and capital allocation.
5. Latest earnings, guidance and material developments.
6. **Competitors:** a justified peer set, dated numeric comparisons, where the target
   is better or worse than each peer, and whether its valuation premium is justified.
7. Bear/base/bull valuation cases and transparent assumptions.
8. Observable market expectations versus the analyst's interpretation.
9. Catalysts and their transmission to earnings or cash flow.
10. Strongest bear case, thesis invalidation and open questions.
11. Price/trend context separated from intrinsic value.
12. Company research milestones and conclusion.
13. Sources and an appended retrieval audit.

The protocol distinguishes a superior business from a superior investment at the
current price. It permits attractive, fairly valued, unattractive and insufficient
evidence conclusions. It imposes no personal CAGR target, allocation limits or
forced doubling thesis. Sector-specific methods matter: banks, REITs, cyclicals and
pre-revenue companies cannot all be evaluated with the same ratios.

## How research runs

The ticker form starts a **fresh investigation**. It does not include older chats or
legacy portfolio notes. Python first attempts to retrieve target metrics, annual and
interim/current SEC filings, current earnings/news, and competitive context. The model
then fills gaps using the shared tool dispatcher.

- `get_financial_metrics`: vendor financials, up to four annual/eight quarterly
  periods where available, source dates/currencies and completed US session prices.
- `get_competitor_metrics`: target plus up to five peers, comparable financial and
  valuation fields, fiscal/currency metadata and explicit comparability warnings.
- `get_sec_filing`: annual, interim and current report excerpts with source metadata.
- `web_search`: current news and discovery; snippets are not full-source evidence.
- `read_source`: bounded text extraction from public URLs already returned in this
  research run. Uses hosted Tavily extraction; direct arbitrary local URL fetching
  is not exposed.
- `calculate_valuation`: checked terminal per-share or enterprise-multiple scenario
  arithmetic. This checks math, not the truth of forecast assumptions; it is not DCF.

Every dispatched tool return receives an evidence ID and retrieval timestamp.
The proposer is given the initial packet and required to gather peer metrics.
One bounded revision attempt addresses missing headings or missing target/peer data.
A different provider can then challenge the draft, including competitor claims,
accounting, citations, scenario math and valuation. The report preserves dissent.

Code checks report headings, basic retrieval coverage, evidence IDs, returned URLs and
some comparability gaps. **These checks do not verify every claim, rank stocks, enforce
an intrinsic-value model, or prove the latest earnings were found.** Missing sections
or retrievals stay visible. Two-model agreement is not proof of investment accuracy.

## Models and failure behavior

Defaults are `claude-opus-5-5`, `gpt-6.1-sol` and `gemini-3.1-pro`, with environment
overrides. Claude streams full messages; OpenAI Responses preserves reasoning and
function-call state with `store=False`; Gemini preserves signed tool content.
Each provider loop has a 12-iteration limit. A full report can also use one repair
pass and one independent review, so cost and latency vary with research depth.

Incomplete, empty or exhausted provider responses fail explicitly. If the proposer
fails, the alternate provider may produce a clearly labeled **unchallenged fallback**.
A failed challenger never becomes an invented second opinion. Data-tool failures can
produce a report with gaps, clearly identified in the report and JSON evidence export.

## Using the app

Sign in, choose an AI model and optionally a different provider for independent
challenge, enter a ticker, then click **Research stock**. Ask follow-ups inside the
resulting stock conversation. Follow-ups are labeled unchallenged; run the ticker form
again for a refreshed full report. They do not inherit personal portfolio notes.

Research history and full report/evidence JSON are saved per user. Download Markdown,
research JSON, or PDF when native rendering is available. Old conversations remain
readable as archives, but are not used to seed new ticker research. The old portfolio
workspace is no longer exposed or read by the app; its stored data is retained rather
than destructively deleted. Watchlist management is not part of this independent app.

See [the detailed guide](docs/independent-research-guide.md) and
[setup instructions](SETUP_AND_RUN.md). The previous local Word guide describes the
superseded portfolio-workspace design and should not be used as current instructions.

## Setup

Use Python 3.12 and install `requirements.txt` in a virtual environment. Copy
`.env.example` to `.env` and `.streamlit/secrets.example.toml` to
`.streamlit/secrets.toml`; keep real secrets out of Git.

| Setting | Purpose |
|---|---|
| ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY | At least one research provider; a second enables independent review |
| TAVILY_API_KEY | Search and substantive source extraction |
| SEC_IDENTITY | Real contact name and email for EDGAR |
| CLAUDE_MODEL / OPENAI_MODEL / GEMINI_MODEL | Optional model ID overrides |
| ALLOWED_EMAILS | Optional authorization allowlist after OIDC login |
| DB_PATH | SQLite location; default `data/alpha_scout.db` |

Configure OIDC redirect URI, cookie secret, client ID, client secret and provider
metadata URL in Streamlit secrets. Register the callback with the identity provider.
Run `streamlit run app.py`. If no provider key is configured, research cannot complete.
Missing native PDF libraries do not prevent research or Markdown downloads.

The Docker image runs as an unprivileged user and includes PDF dependencies. Mount
`/app/data` persistently. Streamlit Community Cloud local storage is not a durable
production database; plan backups/storage before relying on saved history. OIDC user
isolation does not encrypt SQLite. Research requests and context go to the selected
providers; source tools also use their external services.

## Validation and boundaries

Run `python -m pytest -q`. Tests cover provider continuity/failures, ticker isolation,
legacy-data nonuse, user ownership, peer gaps, evidence provenance, scenario math,
financial dates, completed US sessions and safe exports. The `evals/` rubric evaluates
research quality separately; passing software tests does not establish investment
performance. Live provider keys, credits and model access remain operational inputs.

The NYSE session calendar is used only for recognized US exchanges; unsupported
exchange histories are labeled unavailable. SEC coverage and vendor history are not
complete global coverage. Missing data stays missing. No guarantee of returns, market
prediction, expert superiority, automatic trade approval or broker execution is made.

## Implementation map

- `app.py`: authenticated ticker form, history, follow-ups and downloads.
- `stock_research.py`: evidence gathering, report requirements, repair and challenge.
- `research_evidence.py`: request-local provenance and discovered-source URL scope.
- `analysis_protocol.md`: independent underwriting and competitor standards.
- `search_agent.py`: provider loops and tool dispatch.
- `metrics.py`, `market_sessions.py`, `valuation.py`: data and arithmetic.
- `database.py`: user-scoped conversations and atomic research report persistence.
- `report_safety.py`: HTML sanitization and blocked PDF resource loading.
- `research_workspace.py`: legacy storage validation only, not part of research.

GitHub Actions runs software tests on pull requests and main/master pushes. This
repository does not schedule Gmail newsletters, monitor portfolios or synchronize
holdings with the other project.
