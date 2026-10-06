# How Alpha Scout independent research works

Alpha Scout studies one listed company at a time, on its own business economics and
valuation. Entering a ticker is enough. It does not ask what you own, how much cash you
have, where you invest or what portfolio return you target. Portfolio work is handled
by alpha-scout-research, a separate project with a different mandate and data model.

## The research experience

1. Sign in through the configured identity provider.
2. Select the analyst provider. Select a different provider for independent challenge
   if available; that adds API usage and scrutiny, not a guarantee of correctness.
3. Enter the ticker and choose Research stock. Every submission starts fresh research,
   without carrying over previous ticker discussions or saved portfolio context.
4. Read the report's evidence/completeness warnings, then its verdict and analysis.
5. Compare the main report with the independent challenge. Unresolved disagreements
   remain visible rather than being concealed in a consensus summary.
6. Download the report and research JSON if you need a dated record. Follow-ups are
   discussion of that stock and are explicitly unchallenged; rerun the ticker for a
   full refresh.

A report may finish despite a missing source, because useful analysis can still be
possible. Its gap list must make that limitation visible. A failed model request is
not a completed research memo. Fallback research is not independently challenged.

## The starting evidence packet

Python attempts four retrievals before the proposer starts: company metrics, SEC
filings, current earnings/developments search and competitive context search. Each
return gets an evidence ID and UTC retrieval time. The proposer receives those returns
and can request additional metrics, filings, searches, source text and valuation math.
Evidence is stored per research run, not in shared mutable global state.

Source IDs establish which tool return is being referenced. They do not prove that
its content is correct or supports the interpretation. Direct URLs, publication dates,
financial periods and source limitations still matter. A retrieved search snippet is
not a complete filing or transcript. Source reading extracts bounded text from URLs
returned by this run's tools; it does not grant the model arbitrary local-file access.

Annual/interim/current SEC coverage can miss earnings attachments and foreign-issuer
releases. A recent 6-K can be administrative. The protocol directs the analyst to
identify actual earnings disclosures and to label missing evidence. The program does
not certify that the latest earnings release has been found.

## The competitor analysis

The analyst must justify three to five economically relevant public peers, or explain
why a smaller set is more appropriate. It considers products, customers, revenue models
and industry structure, rather than selecting companies merely because they share a
popular theme. The peer tool gathers data for the target and up to five peers.

The memo should show dated growth, gross/operating margin, FCF margin/yield, capital
returns where applicable, SBC/dilution, leverage and suitable valuation multiples. It
should also explain which metrics are inappropriate for the sector. Different fiscal
periods and currencies are explicit comparability warnings, not permission to rank
incompatible figures.

For each peer, the memo must identify where the target is stronger and weaker, cite
the numeric evidence and explain the business reason. It must then assess whether the
valuation premium or discount is justified. Faster growth does not automatically mean
a better investment when the stock is much more expensive. Conversely, a cheaper
multiple can reflect inferior economics or refinancing risk.

If competitor data is missing, the workflow gives the proposer one chance to repair
coverage. If it remains missing, the report carries a visible gap. The completeness
check detects whether target/peer data was retrieved; it does not independently judge
the chosen peer set or every better/worse claim. That remains a subject for the model
challenge and research-quality evaluation.

## Financial and valuation standards

The metrics tool includes available annual and quarterly history with period-end
labels and missing values preserved. Availability can be less than four years or eight
quarters. Quarterly figures are not automatically TTM. Income/cash-flow period mismatch
suppresses some derived ratios, and ROIC is labeled an ending-capital estimate.

The analyst investigates reported earnings versus cash, capex and working capital,
SBC and diluted shares, debt/cash, refinancing needs and capital allocation. It should
use sector-appropriate measures: for example, bank credit/funding and capital, REIT
FFO/AFFO, midcycle commodity earnings, or biotech runway and clinical milestones.

The valuation calculator supports two explicit methods. For an equity per-share
multiple, terminal EPS/FCF/FFO/book value per share is multiplied by an exit multiple.
For an enterprise multiple, the terminal company metric is multiplied by its multiple,
net debt is subtracted, equity value is floored at zero, and the result is divided by
terminal shares. Company metrics, debt and shares must use matching units. Negative
or nonfinite unsupported inputs are rejected.

Bear/base/bull cases produce future target prices and annualized returns over the
stated horizon. Optional cumulative dividends are treated as terminal accumulated cash,
not reinvested income. These are arithmetic results from analyst assumptions, not
verified forecasts or today's fair value. A present-value estimate requires an
explicit discount-rate/timing model; the tool does not claim to calculate DCF.

## Report structure and review

The thirteen required sections cover the research verdict; business economics;
financial history/earnings quality; balance sheet/capital allocation; latest earnings;
peers; valuation/scenarios; market expectations; catalysts; bear case/invalidation;
price context; open questions/conclusion; and sources. A section can explain a data gap
or why a metric is inapplicable, rather than filling the space with invented precision.

A second provider can audit the draft using the same evidence packet and new tools.
The review specifically challenges competitor claims, period/currency compatibility,
source support, accounting choices and valuation math. The reviewer is not the same
provider as the proposer. A fallback provider cannot challenge its own fallback report.

The application also flags missing headings, unknown evidence IDs, URLs not present in
retrievals, missing baseline data, retrieval/calculation errors and peer comparability
issues. These checks are transparency measures. A report passing them is not certified
investment research, and a second model can still repeat the first model's error.

## Storage and project separation

New research runs are saved atomically with a user-owned conversation and the full
report/evidence payload. Another user cannot load the report through the application's
database API. OIDC authentication and an optional email allowlist control access.
SQLite itself is not encrypted by this application; administrators with filesystem
access can read it. External providers receive the research requests and conversation.

Archived conversations remain readable but do not seed new ticker investigations.
The former portfolio workspace is removed from the UI and research request path. Its
database records are retained for recovery rather than deleted. It does not block or
personalize a stock report. The app has no watchlist maintenance, portfolio import,
portfolio sizing, account recommendations, monitoring schedule or brokerage connection.

Save Markdown or the full research JSON for portability. PDFs appear when the native
renderer works; HTML is sanitized and local/network resources are blocked during PDF
rendering. Back up SQLite using a consistent snapshot and persistent storage. A JSON
report download is not a built-in database restore/import mechanism.

## What has and has not been established

Regression tests verify software behavior, isolation and arithmetic. They cannot prove
that generated research is accurate, exhaustive or better than a human analyst. The
evaluation rubric should assess primary-source support, sector appropriateness,
competitor reasoning and forecast humility across industries and provider failures.
Model availability, billing, API rate limits and source access must be monitored in the
actual deployment. Main-branch Git state is not proof of a successful hosted deployment.


### Validation of this update

The implementation passed 58 automated tests covering isolation, provider routing,
source handling, missing data, period alignment and valuation arithmetic. A live MSFT
run using Claude produced all thirteen sections, four competitor comparisons and
valuation calculations. This smoke test does not establish accuracy across stocks.

The live environment had three unresolved external limitations: OpenAI reported an
exhausted credit balance; Google's configured Gemini model returned 404/not supported;
and SEC document extraction returned metadata without filing text, including after
the fallback attempt. Reports retain explicit warnings for these conditions. Restoring
reviewer access and primary filing extraction remains necessary for fuller coverage.
