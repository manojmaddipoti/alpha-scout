# Alpha Scout

A sophisticated AI-powered market analysis tool that provides deep financial insights and investment analysis using multiple AI models and real-time market data.

## Overview

This application combines advanced AI models (GPT-4o, Google Gemini) with financial data APIs to deliver comprehensive stock analysis. It evaluates companies against growth benchmarks, technical indicators, and fundamental metrics to help identify high-conviction investment opportunities.

## Key Features

- **Multi-Model AI Support**: Leverage GPT-4o, Gemini-3-Pro, or Deep Research models
- **Comprehensive Analysis Framework**: Evaluates stocks using the "Beat QQQ" strategy
- **Real-Time Market Data**: Integration with Yahoo Finance for current pricing and historical trends
- **SEC Filings Analysis**: Automated retrieval and analysis of 10-K/10-Q/20-F filings
- **Web Research**: Real-time news and analyst ratings via Tavily search
- **Advanced Metrics**: Magic Number, Rule of 40, PEG ratios, and more
- **Interactive UI**: Clean Streamlit interface with chat history and PDF export
- **Technical Analysis**: 200-day moving averages, RSI indicators, momentum signals

## Analysis Methodology

The agent applies a rigorous investment framework:

1. **Business Quality Assessment**: Moat analysis, business model evaluation
2. **Financial Screening**: Growth rates, profitability, cash flow metrics
3. **Technical Analysis**: Trend identification, momentum indicators
4. **Risk Evaluation**: SEC filing risk factors, competitive analysis
5. **Investment Verdict**: Clear buy/hold/sell recommendations with reasoning

## Installation

### Prerequisites

- Python 3.10 or higher
- API keys for OpenAI, Google Gemini, and Tavily

### Local Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd alpha-scout
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

5. Run the application:
```bash
streamlit run app.py
```

### Docker Deployment

Build and run using Docker:

```bash
docker build -t alpha-scout .
docker run -p 8501:8501 --env-file .env alpha-scout
```

## Configuration

Create a `.env` file with the following variables:

```env
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
TAVILY_API_KEY=your_tavily_api_key
SEC_IDENTITY=Your Name your@email.com
APP_PASSWORD=your_app_password
```

## Usage

1. Launch the application and log in with your access code
2. Select an AI model from the sidebar
3. Ask questions about stocks (e.g., "Analyze NVDA" or "Compare MSFT and GOOGL")
4. Review the comprehensive analysis including:
   - Business model and competitive moat
   - Financial metrics and growth rates
   - Technical indicators and price trends
   - Bull/bear case analysis
   - Investment recommendation

5. Export reports as PDF for later reference

## Project Structure

```
alpha-scout/
├── app.py              # Main Streamlit application
├── search_agent.py     # AI agent logic and tool functions
├── database.py         # SQLite chat history management
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container configuration
├── .env.example        # Environment variables template
└── README.md          # Project documentation
```

## Technology Stack

- **Frontend**: Streamlit
- **AI Models**: OpenAI GPT-4o, Google Gemini 3.0, Deep Research
- **Financial Data**: yfinance, SEC EDGAR tools
- **Web Search**: Tavily API
- **Database**: SQLite
- **Report Generation**: FPDF2

## Key Metrics Explained

- **Magic Number**: Sales efficiency metric (Net New ARR / Sales & Marketing Spend)
- **Rule of 40**: Growth rate + profit margin (benchmark for SaaS companies)
- **PEG Ratio**: Price/Earnings to Growth ratio (valuation metric)
- **Capex Coverage**: Operating cash flow relative to capital expenditures

## Security Notes

- The application includes password authentication
- API keys are stored in environment variables
- Database files are created in writable directories only
- No sensitive data is logged or stored in version control

## Development

To contribute or modify:

1. Follow the existing code structure and style
2. Test changes locally before deploying
3. Update documentation for new features
4. Ensure environment variables are properly configured

## Troubleshooting

**Database errors**: Ensure `/tmp/data` directory is writable
**API failures**: Verify all API keys are valid and properly configured
**Import errors**: Reinstall dependencies with `pip install -r requirements.txt`
**Model access**: Some Gemini models require specific API access levels

## License

This project is for educational and personal use.

## Contact

For questions or feedback, please open an issue in the repository.
