# Alpha Scout

Alpha Scout is a private Streamlit research workspace for forensic single-stock underwriting. Give it any public ticker in any industry and it will build a buy-side thesis around one question: is this a true 1-3 year double candidate, or a durable compounder worth owning even if a quick double is unrealistic?

The app is intentionally aggressive, but not blindly bullish. It forces each model to prove the 2x math, compare real public competitors, read financial quality, inspect SEC filings, identify catalysts, and define kill criteria.

## Key Features

- **Three independent model families**: Claude, OpenAI, and Gemini selectable from the sidebar.
- **Configurable current models**: Defaults live in `model_config.py` and can be overridden with `.env` variables. Claude defaults to Opus 4.8 for a better cost/capability tradeoff than Fable.
- **Industry-agnostic analysis**: The protocol adapts to software, payments, industrials, energy, semis, biotech, consumer, financials, and other public-company models.
- **Forensic financial metrics**: True ROIC, operating cash flow, free cash flow, FCF yield, FCF/share, SBC/OCF, dilution, revenue growth, Rule of 40, Magic Number, moving averages, and RSI.
- **Competitor matrix**: The agent can compare the target against public peers instead of analyzing a company in isolation.
- **SEC filing teardown**: Pulls MD&A and risk-factor sections from recent filings where available.
- **Real-time web research**: Uses Tavily for recent catalysts, management commentary, news, and market context.
- **Downloadable reports**: Export every assistant thesis as Markdown or PDF.
- **Private access gate**: Requires `APP_PASSWORD`; there is no hardcoded fallback password.

## Analysis Methodology

The system prompt lives in `analysis_protocol.md`. It requires a structured memo with:

1. **Verdict**: STRONG BUY, WATCHLIST, or AVOID.
2. **2x Probability**: horizon, confidence, and explicit base/bull/bear framing.
3. **2x Market-Cap Math**: revenue, margin, multiple, dilution, and FCF assumptions needed for a double.
4. **Business Reality**: how the company actually makes money and where it sits in the value chain.
5. **Competitor Matrix**: public peers, growth, profitability, valuation, and moat comparison.
6. **Variant Perception**: what the market likely believes and what must be wrong for alpha.
7. **Catalyst Timeline**: events that can re-rate the stock over the next 1-3 years.
8. **Management And Capital Allocation**: insider behavior, dilution, buybacks, M&A, and execution quality.
9. **Financial Quality**: cash conversion, ROIC, FCF, SBC, leverage, and technical trend.
10. **Bear Case And Kill Criteria**: measurable signals that invalidate the thesis.

## Installation

### Prerequisites

- Python 3.10 or higher
- API keys for Anthropic, OpenAI, Google Gemini, and Tavily

### Local Setup

```bash
git clone <repository-url>
cd alpha-scout
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your API keys and a strong `APP_PASSWORD`.

Run the app:

```bash
streamlit run app.py
```

### Docker Deployment

```bash
docker build -t alpha-scout .
docker run -p 8501:8501 --env-file .env alpha-scout
```

## Configuration

Required `.env` values:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
TAVILY_API_KEY=your_tavily_api_key
SEC_IDENTITY=Your Name your@email.com
APP_PASSWORD=your_private_access_code
```

Optional model overrides:

```env
OPENAI_MODEL=gpt-5.5
CLAUDE_MODEL=claude-opus-4-8
GEMINI_MODEL=gemini-3.1-pro
```

Model availability changes over time. When providers release stronger models or retire older ones, update these three values in `.env` or `model_config.py`.

## Usage

1. Launch the app and log in with your access code.
2. Select Claude, OpenAI, or Gemini in the sidebar.
3. Ask for a ticker thesis, for example:

```text
Analyze FOUR for a 1-3 year double. Include competitors, valuation math, catalysts, bear case, and kill criteria.
```

4. Review the generated thesis, price chart, and competitor/financial analysis.
5. Download the report as Markdown for editing or PDF for archive/sharing.

## Project Structure

```text
alpha-scout/
├── analysis_protocol.md  # Industry-agnostic underwriting protocol
├── app.py                # Streamlit chat UI and report exports
├── config.py             # Environment-backed app configuration
├── database.py           # SQLite chat history management
├── metrics.py            # Corrected financial and competitor metrics
├── model_config.py       # Central model defaults and model dropdown choices
├── search_agent.py       # Multi-model agent logic and tool calling
├── requirements.txt      # Runtime dependencies
├── Dockerfile            # Container configuration
├── .env.example          # Environment variable template
└── README.md
```

## Technology Stack

- **Frontend**: Streamlit
- **AI Providers**: Anthropic Claude, OpenAI, Google Gemini
- **Financial Data**: yfinance, SEC EDGAR tools
- **Web Search**: Tavily API
- **Database**: SQLite
- **Report Generation**: Markdown and WeasyPrint PDF

## Security Notes

- Set a strong `APP_PASSWORD`; the app refuses to start without one.
- Keep `.env` local and out of version control.
- Store production secrets in GitHub/hosting secrets, not in code.
- Rotate any API key that was committed, pasted into logs, or shared outside your machine.

## Troubleshooting

- **Login does not appear**: Confirm `APP_PASSWORD` is set.
- **API failures**: Verify provider keys and model access.
- **SEC filing errors**: Confirm `SEC_IDENTITY` is a real name and email format.
- **Database errors**: Ensure `/tmp/data` is writable, or set `DB_PATH`.
- **PDF errors**: WeasyPrint may require system libraries on some machines.
