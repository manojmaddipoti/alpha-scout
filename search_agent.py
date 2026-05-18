import os
import json
import time
import yfinance as yf
from openai import OpenAI
from tavily import TavilyClient
from google import genai
import anthropic
from dotenv import load_dotenv

load_dotenv()

# Client Initialization Functions
def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found")
    return OpenAI(api_key=api_key)

def get_tavily_client():
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not found")
    return TavilyClient(api_key=api_key)

def get_gemini_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found")
    return genai.Client(api_key=api_key)

def get_claude_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found")
    return anthropic.Anthropic(api_key=api_key)

# System Prompt
SYSTEM_PROMPT = """
You are an Elite Buy-Side Equities Analyst at a top-tier hedge fund. 
Your mandate is to generate high-conviction, proprietary investment theses. You do not follow market consensus; you exploit it by identifying what the market is mispricing.

You are evaluating a potential addition to a concentrated, high-performance portfolio. You must evaluate the company from first principles, acting as a forensic accountant and a ruthless business strategist. 

When analyzing ANY stock, use your tools (`get_financial_metrics`, `get_sec_filing`, `web_search`) to execute the following deep-dive framework:

### 1. 🏢 Business Reality & The Moat (No Buzzwords)
- **The Economic Engine:** Explain exactly how this company extracts cash from its customers. Strip away the corporate jargon. What is the actual product/service?
- **The Structural Moat:** Does this company have a genuine, unassailable moat, or just a temporary head start? Assess switching costs, network effects, cost advantages, or intangible assets.
- **The Value Chain:** Where does this company sit in its industry's value chain? Who holds the power: them, their suppliers, or their customers?

### 2. 🕵️ Forensic Accounting & Capital Allocation
*Contextualize the numbers. Do not just list them; interpret what they mean for the business lifecycle.*
- **Capital Efficiency:** Evaluate `return_on_invested_capital` (ROIC) and margins. Is management effectively compounding capital, or are they destroying it to buy growth?
- **True Cash Generation:** Analyze Free Cash Flow relative to `stock_based_comp`. Is the cash flow real, or is it an illusion created by diluting shareholders?
- **The Balance Sheet:** Evaluate debt, cash reserves, and `capex_coverage_percent`. Can they self-fund their operations and growth, or are they dependent on capital markets?

### 3. 📜 The SEC Tape (Filing Analysis)
*You MUST use `get_sec_filing` to read the actual filings (10-K, 10-Q). Do not rely solely on press releases.*
- **Management's Tone (MD&A):** What is management emphasizing in the Management's Discussion and Analysis? Are they hiding deterioration behind "adjusted" metrics?
- **The Hidden Risks:** Identify the specific, material "Risk Factors" listed in the filings. Ignore boilerplate legal warnings; find the actual existential threats (e.g., customer concentration, severe supply chain chokepoints, pending regulatory doom).

### 4. 🧠 The Variant Perception (The Hedge Fund Edge)
*This section is now data-driven. Do not guess what consensus thinks — read it from the metrics.*
- **The Consensus, Quantified:** Pull `analyst_consensus`, `analyst_target_mean`, and `upside_to_target_percent` from `get_financial_metrics`. The Street's view is no longer abstract — it is a specific price and recommendation.
- **Smart Money Signal:** Check `insider_net_shares_6mo`. Insiders buying their own stock with personal cash is one of the highest-signal alpha factors in equities. Heavy net buying contradicting a bearish consensus = high-conviction variant setup. Heavy net selling alongside a bullish consensus = warning.
- **Crowded Trade Check:** Read `short_percent_of_float` and `short_ratio_days_to_cover`. >10% short with low days-to-cover = squeeze potential if your bull thesis is right. >5% short with high days-to-cover = crowded short, harder to compress. Low short interest on a bear thesis = your idea is not contrarian.
- **Your Variant Perception:** Given consensus is *X* and the data shows *Y*, where exactly is the market wrong? What hidden catalyst, structural shift, or misread metric proves the current valuation is incorrect?

### 5. ⚖️ Asymmetric Risk/Reward Assessment
- **The Bull Case (Upside Convexity):** If your variant perception is correct, how does the business scale? What is the specific catalyst that forces the market to re-price the stock higher?
- **The Bear Case (Margin of Safety):** If you are wrong, how much capital is permanently destroyed? What is the fundamental floor for this stock?

### 6. 🏛️ The Portfolio Manager's Verdict
Present a definitive, cutthroat investment conclusion.
- State clearly if the stock is a **STRONG BUY**, **HOLD**, or **AVOID/SHORT**.
- Justify the verdict based entirely on the alignment of its intrinsic business quality, its capital allocation track record, and the current mispricing in the market. Do not let a great company distract you if it is priced for an impossible perfection. Do not let a temporary ugly quarter scare you away from a structural monopoly.
"""

# Tool Functions

def get_sec_filing(ticker: str):
    """Fetch latest 10-K/10-Q and surgically extract Item 7 (MD&A) and Item 1A (Risk Factors)."""
    try:
        import re
        from edgar import Company, set_identity

        sec_identity = os.getenv("SEC_IDENTITY", "Agent user@example.com")
        set_identity(sec_identity)

        company = Company(ticker)

        annual = company.get_filings(form=["10-K", "20-F"])
        latest_annual = annual.latest() if annual else None

        quarterly = company.get_filings(form=["10-Q", "6-K"])
        latest_quarter = quarterly.latest() if quarterly else None

        # Prefer 10-K — MD&A and Risk Factors are far more comprehensive in annual reports.
        filing = latest_annual or latest_quarter
        if not filing:
            return f"No recent SEC filings found for {ticker}."

        source_used = f"{filing.form} ({filing.filing_date})"
        mda_text = ""
        risk_text = ""

        # Try edgartools' structured accessors first — they vary by version.
        try:
            filing_obj = filing.obj()
            for attr in ("management_discussion", "mda", "item_7"):
                if hasattr(filing_obj, attr):
                    val = getattr(filing_obj, attr)
                    if val:
                        mda_text = str(val)
                        break
            for attr in ("risk_factors", "item_1a"):
                if hasattr(filing_obj, attr):
                    val = getattr(filing_obj, attr)
                    if val:
                        risk_text = str(val)
                        break
        except Exception:
            pass

        # Fallback: regex extraction from full filing text.
        if not mda_text or not risk_text:
            full_text = filing.text()

            if not risk_text:
                m = re.search(
                    r"Item\s*1A\.?\s*Risk\s*Factors(.{500,80000}?)(?=Item\s*1B|Item\s*2\.?\s*Properties)",
                    full_text, re.IGNORECASE | re.DOTALL
                )
                if m:
                    risk_text = m.group(1).strip()

            if not mda_text:
                m = re.search(
                    r"Item\s*7\.?\s*Management.{0,80}Discussion(.{500,80000}?)(?=Item\s*7A|Item\s*8\.?\s*Financial)",
                    full_text, re.IGNORECASE | re.DOTALL
                )
                if m:
                    mda_text = m.group(1).strip()

        parts = [f"**Source:** {source_used}"]
        if mda_text:
            parts.append(f"\n**Item 7 — Management's Discussion & Analysis (MD&A):**\n{mda_text[:12000]}")
        else:
            parts.append("\n**Item 7 (MD&A):** Could not extract — section heading not found.")
        if risk_text:
            parts.append(f"\n**Item 1A — Risk Factors:**\n{risk_text[:12000]}")
        else:
            parts.append("\n**Item 1A (Risk Factors):** Could not extract — section heading not found.")

        return "\n".join(parts)

    except Exception as e:
        return f"Error fetching SEC filings for {ticker}: {str(e)}"


def get_financial_metrics(ticker: str):
    """Fetch comprehensive financial metrics including valuation, growth, and technical indicators."""
    for attempt in range(3):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if info and "currentPrice" in info:
                break
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 2:
                return json.dumps({"error": f"Rate limit or network error fetching data for {ticker}. Please retry."})
            time.sleep(2 ** attempt)

    try:
        if not info or "currentPrice" not in info:
            return json.dumps({"error": f"Invalid ticker: {ticker}"})

        financials = stock.financials
        quarterly_financials = stock.quarterly_financials
        cashflow = stock.cashflow

        # Basic Valuation
        fwd_pe = info.get("forwardPE")
        peg = info.get("pegRatio")

        if peg is None and fwd_pe:
            growth_est = info.get("earningsGrowth", 0)
            if growth_est and growth_est > 0:
                peg = round(fwd_pe / (growth_est * 100), 2)

        # Advanced Metrics
        revenue_cagr_3yr = "N/A"
        ocf_cagr_3yr = "N/A"
        capex_coverage = "N/A"
        share_count_growth = "N/A"
        sbc_percent = "N/A"
        magic_number = "N/A"
        ocf_val = 0
        sbc_val = 0

        try:
            # SaaS Magic Number
            if not quarterly_financials.empty and "Total Revenue" in quarterly_financials.index:
                q_revs = quarterly_financials.loc["Total Revenue"]
                sm_row = next((idx for idx in quarterly_financials.index if "Selling" in str(idx) and "Marketing" in str(idx)), None)
                
                if sm_row and len(q_revs) >= 2:
                    rev_q0 = q_revs.iloc[0]
                    rev_q1 = q_revs.iloc[1]
                    sm_expenses = quarterly_financials.loc[sm_row]
                    sm_q1 = sm_expenses.iloc[1]
                    
                    if sm_q1 > 0:
                        net_new_rev_annualized = (rev_q0 - rev_q1) * 4
                        magic_val = net_new_rev_annualized / sm_q1
                        magic_number = round(magic_val, 2)

            # Revenue CAGR
            if not financials.empty and "Total Revenue" in financials.index:
                revs = financials.loc["Total Revenue"]
                if len(revs) >= 4:
                    curr = revs.iloc[0]
                    past = revs.iloc[3]
                    if past > 0:
                        revenue_cagr_3yr = round(((curr / past) ** (1/3) - 1) * 100, 2)

            # OCF & CapEx Coverage
            capex_val = 0
            
            if not cashflow.empty:
                ocf_row = next((idx for idx in cashflow.index if "Operating" in str(idx) and "Cash" in str(idx)), None)
                if ocf_row:
                    ocf_val = cashflow.loc[ocf_row].iloc[0]
                    ocfs = cashflow.loc[ocf_row]
                    if len(ocfs) >= 4 and ocfs.iloc[3] > 0:
                        ocf_cagr_3yr = round(((ocfs.iloc[0] / ocfs.iloc[3]) ** (1/3) - 1) * 100, 2)

                capex_row = next((idx for idx in cashflow.index if "Capital" in str(idx) and "Expenditure" in str(idx)), None)
                if not capex_row:
                     capex_row = next((idx for idx in cashflow.index if "Purchase" in str(idx) and "PPE" in str(idx)), None)
                
                if capex_row:
                    capex_val = cashflow.loc[capex_row].iloc[0]

                if capex_val != 0:
                    coverage = ocf_val / abs(capex_val)
                    capex_coverage = round(coverage * 100, 2)

            # D. Share Count Growth
            if not financials.empty:
                shares_row = next((idx for idx in financials.index if "Diluted Average Shares" in str(idx)), None)
                if not shares_row:
                    shares_row = next((idx for idx in financials.index if "Basic Average Shares" in str(idx)), None)
                
                if shares_row:
                    shares = financials.loc[shares_row]
                    if len(shares) >= 2:
                        curr_shares = shares.iloc[0]
                        last_year_shares = shares.iloc[1]
                        if last_year_shares > 0:
                            growth = (curr_shares / last_year_shares) - 1
                            share_count_growth = round(growth * 100, 2)

            # SBC %
            if not cashflow.empty:
                sbc_row = next((idx for idx in cashflow.index if "Stock" in str(idx) and "Compensation" in str(idx)), None)
                if sbc_row:
                    sbc_val = cashflow.loc[sbc_row].iloc[0]
                    if info.get("totalRevenue"):
                        sbc_percent = round((sbc_val / info.get("totalRevenue")) * 100, 2)

        except Exception:
            pass

        # Cash quality: is SBC eating most of OCF? (forensic — shareholder value transfer)
        sbc_to_ocf = "N/A"
        if sbc_val and ocf_val and ocf_val > 0:
            sbc_to_ocf = round((sbc_val / ocf_val) * 100, 2)

        # Technicals & Rule of 40
        history = stock.history(period="1y")
        price_above_200dma = "N/A"
        rsi_14 = "N/A"
        
        if not history.empty and len(history) > 200:
            sma_200 = history["Close"].rolling(window=200).mean().iloc[-1]
            price_above_200dma = True if history["Close"].iloc[-1] > sma_200 else False
            
            delta = history["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_14 = round(100 - (100 / (1 + rs.iloc[-1])), 2)

        rule_of_40 = "N/A"
        rev_growth = info.get("revenueGrowth", 0)
        fcf_margin = 0
        if info.get("totalRevenue") and info.get("freeCashflow"):
            fcf_margin = info.get("freeCashflow") / info.get("totalRevenue")
        elif info.get("ebitdaMargins"):
            fcf_margin = info.get("ebitdaMargins")
            
        if rev_growth is not None:
            rule_of_40 = round((rev_growth * 100) + (fcf_margin * 100), 2)

        # Alpha Signal Block — insider buying, consensus, short interest

        # Insider activity: positive = net buying (executives accumulating with personal cash)
        insider_net_shares_6mo = "N/A"
        try:
            ins = stock.insider_purchases
            if ins is not None and not ins.empty:
                label_col = ins.columns[0]
                net_row = ins[ins[label_col].astype(str).str.contains("Net", case=False, na=False)]
                if not net_row.empty and len(ins.columns) > 1:
                    val = net_row.iloc[0, 1]
                    if val is not None and str(val).strip() not in ("", "nan"):
                        insider_net_shares_6mo = int(val)
        except Exception:
            pass

        # Analyst consensus — needed for variant perception (where is the Street wrong?)
        target_mean = info.get("targetMeanPrice")
        current_price = info.get("currentPrice")
        upside_to_target = "N/A"
        if target_mean and current_price:
            upside_to_target = round(((target_mean / current_price) - 1) * 100, 2)

        # Short interest — contrarian / squeeze signal
        short_pct = info.get("shortPercentOfFloat")
        short_pct_float = round(short_pct * 100, 2) if short_pct else "N/A"

        # Compile Results
        data = {
            "ticker": ticker.upper(),
            "price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "forward_pe": fwd_pe,
            "peg_ratio": peg,
            "return_on_invested_capital": round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else "N/A",
            "operating_cash_flow": ocf_val if ocf_val else "N/A",
            "magic_number": magic_number,
            "revenue_growth_yoy": round(rev_growth * 100, 2) if rev_growth else "N/A",
            "revenue_cagr_3yr": revenue_cagr_3yr,
            "capex_coverage_percent": capex_coverage,
            "share_count_growth_yoy": share_count_growth,
            "sbc_percent_revenue": sbc_percent,
            "sbc_to_ocf_percent": sbc_to_ocf,
            "rule_of_40": rule_of_40,
            "price_above_200dma": price_above_200dma,
            "rsi_14_day": rsi_14,
            "gross_margin": round(info.get("grossMargins", 0) * 100, 2) if info.get("grossMargins") else "N/A",
            "net_cash": (info.get("totalCash", 0) or 0) - (info.get("totalDebt", 0) or 0),
            "insider_net_shares_6mo": insider_net_shares_6mo,
            "analyst_consensus": info.get("recommendationKey", "N/A"),
            "analyst_count": info.get("numberOfAnalystOpinions", "N/A"),
            "analyst_target_mean": target_mean if target_mean else "N/A",
            "analyst_target_high": info.get("targetHighPrice", "N/A"),
            "analyst_target_low": info.get("targetLowPrice", "N/A"),
            "upside_to_target_percent": upside_to_target,
            "short_percent_of_float": short_pct_float,
            "short_ratio_days_to_cover": info.get("shortRatio", "N/A"),
            "business_summary": info.get("longBusinessSummary", "N/A")
        }

        return json.dumps(data)

    except Exception as e:
        return json.dumps({"error": f"Error fetching financials for {ticker}: {str(e)}"})

def web_search(query: str):
    """Search the web for recent news and information using Tavily."""
    try:
        tavily = get_tavily_client()
        results = tavily.search(query=query, topic="news", search_depth="advanced")
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": f"Search error: {str(e)}"})

# OpenAI Agent Logic

TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current news, analyst consensus, and market sentiment. Use this to identify variant perception — where the Street consensus may be mispricing the stock.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_financial_metrics",
            "description": "Fetch forensic + alpha-signal metrics for a ticker. Includes: forensic accounting (ROIC, operating cash flow, SBC as % of OCF, dilution, capex coverage, net debt, valuation ratios); insider buying (net shares purchased by executives — strong-conviction alpha factor); analyst consensus (recommendation key, mean/high/low price targets, implied upside %); short interest (% of float, days-to-cover). Use this for capital quality, smart-money positioning, and the consensus-vs-reality math required for variant perception.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sec_filing",
            "description": "Retrieve the targeted Item 7 (MD&A) and Item 1A (Risk Factors) sections from the latest 10-K/20-F. Use this to read management's framing in their own words and identify the material existential risks they are legally required to disclose.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]
            }
        }
    }
]

def run_openai_logic(messages):
    """Execute OpenAI function calling logic."""
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS_OPENAI
        )

        assistant_msg = response.choices[0].message
        found_tickers = []
        if assistant_msg.tool_calls:
            messages.append(assistant_msg.model_dump())

            for tool in assistant_msg.tool_calls:
                args = json.loads(tool.function.arguments)
                func_name = tool.function.name
                result = ""
                if func_name == "web_search":
                    result = web_search(args["query"])
                elif func_name == "get_financial_metrics":
                    ticker = args["ticker"]
                    found_tickers.append(ticker)
                    result = get_financial_metrics(ticker)
                elif func_name == "get_sec_filing":
                    ticker = args["ticker"]
                    result = get_sec_filing(ticker)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool.id,
                    "name": func_name,
                    "content": result
                })

            final_response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            return final_response.choices[0].message.content, found_tickers

        return assistant_msg.content, found_tickers

    except Exception as e:
        return f"OpenAI error: {str(e)}", []

# Gemini Agent Logic

def run_gemini_logic(messages, model_name="gemini-2.0-flash-exp"):
    """Execute Gemini function calling logic using new google.genai package."""
    try:
        client = get_gemini_client()

        # Build conversation history
        contents = []
        system_instruction = SYSTEM_PROMPT

        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant" and content:
                contents.append({"role": "model", "parts": [{"text": content}]})

        # Define tools in new format
        tools = [
            {
                "function_declarations": [
                    {
                        "name": "web_search",
                        "description": "Search the web for current news, analyst consensus, and market sentiment. Use this to identify variant perception — where the Street consensus may be mispricing the stock.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "get_financial_metrics",
                        "description": "Fetch forensic + alpha-signal metrics for a ticker. Includes: forensic accounting (ROIC, operating cash flow, SBC as % of OCF, dilution, capex coverage, net debt, valuation ratios); insider buying (net shares purchased by executives — strong-conviction alpha factor); analyst consensus (recommendation key, mean/high/low price targets, implied upside %); short interest (% of float, days-to-cover). Use this for capital quality, smart-money positioning, and the consensus-vs-reality math required for variant perception.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "ticker": {"type": "string", "description": "Stock ticker symbol"}
                            },
                            "required": ["ticker"]
                        }
                    },
                    {
                        "name": "get_sec_filing",
                        "description": "Retrieve the targeted Item 7 (MD&A) and Item 1A (Risk Factors) sections from the latest 10-K/20-F. Use this to read management's framing in their own words and identify the material existential risks they are legally required to disclose.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "ticker": {"type": "string", "description": "Stock ticker symbol"}
                            },
                            "required": ["ticker"]
                        }
                    }
                ]
            }
        ]

        # Generate content with automatic function calling
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config={
                "system_instruction": system_instruction,
                "tools": tools,
                "temperature": 0.7,
            }
        )

        # Handle function calls if any
        tool_calls_made = False
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call is not None:
                    tool_calls_made = True
                    func_call = part.function_call
                    func_name = func_call.name
                    func_args = dict(func_call.args)

                    # Execute the function
                    result = ""
                    if func_name == "web_search":
                        result = web_search(func_args["query"])
                    elif func_name == "get_financial_metrics":
                        result = get_financial_metrics(func_args["ticker"])
                    elif func_name == "get_sec_filing":
                        result = get_sec_filing(func_args["ticker"])

                    contents.append({
                        "role": "model",
                        "parts": [{"function_call": {"name": func_name, "args": func_args}}]
                    })
                    contents.append({
                        "role": "user",
                        "parts": [{"function_response": {"name": func_name, "response": {"result": result}}}]
                    })

        if tool_calls_made:
            final_response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config={"system_instruction": system_instruction}
            )
            return final_response.text, []

        return response.text, []

    except Exception as e:
        return f"Gemini error: {str(e)}", []

# Claude Agent Logic

TOOLS_CLAUDE = [
    {
        "name": "web_search",
        "description": "Search the web for current news, analyst consensus, and market sentiment. Use this to identify variant perception — where the Street consensus may be mispricing the stock.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"]
        }
    },
    {
        "name": "get_financial_metrics",
        "description": "Fetch forensic + alpha-signal metrics for a ticker. Includes: forensic accounting (ROIC, operating cash flow, SBC as % of OCF, dilution, capex coverage, net debt, valuation ratios); insider buying (net shares purchased by executives — strong-conviction alpha factor); analyst consensus (recommendation key, mean/high/low price targets, implied upside %); short interest (% of float, days-to-cover). Use this for capital quality, smart-money positioning, and the consensus-vs-reality math required for variant perception.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"]
        }
    },
    {
        "name": "get_sec_filing",
        "description": "Retrieve the targeted Item 7 (MD&A) and Item 1A (Risk Factors) sections from the latest 10-K/20-F. Use this to read management's framing in their own words and identify the material existential risks they are legally required to disclose.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"]
        }
    }
]

def run_claude_logic(messages, model_name="claude-opus-4-6"):
    """Execute Claude tool-use logic using Anthropic SDK."""
    try:
        client = get_claude_client()

        # Build conversation history (exclude system messages)
        claude_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                claude_messages.append({"role": "user", "content": content})
            elif role == "assistant" and content:
                claude_messages.append({"role": "assistant", "content": content})

        found_tickers = []

        # Agentic tool-use loop
        while True:
            response = client.messages.create(
                model=model_name,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS_CLAUDE,
                messages=claude_messages
            )

            # No tool calls — return final text
            if response.stop_reason != "tool_use":
                final_text = "".join(
                    block.text for block in response.content if hasattr(block, "text")
                )
                return final_text, found_tickers

            # Execute tool calls
            claude_messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                func_name = block.name
                func_args = block.input
                result = ""

                if func_name == "web_search":
                    result = web_search(func_args["query"])
                elif func_name == "get_financial_metrics":
                    ticker = func_args["ticker"]
                    found_tickers.append(ticker)
                    result = get_financial_metrics(ticker)
                elif func_name == "get_sec_filing":
                    result = get_sec_filing(func_args["ticker"])

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

            claude_messages.append({"role": "user", "content": tool_results})

    except Exception as e:
        return f"Claude error: {str(e)}", []


# Main Agent Router
def run_smart_agent(messages, model_choice="gemini-2.5-pro"):
    """Execute the appropriate AI agent based on model selection."""
    try:
        if "gemini" in model_choice.lower():
            return run_gemini_logic(messages, model_choice)
        elif "claude" in model_choice.lower():
            return run_claude_logic(messages, model_choice)
        else:
            return run_openai_logic(messages)
    except Exception as e:
        return f"Agent execution error: {str(e)}", []