import os
import json
import yfinance as yf
import pandas as pd
from openai import OpenAI
from tavily import TavilyClient
import google.generativeai as genai
from google.api_core.exceptions import NotFound, InvalidArgument
from dotenv import load_dotenv

# REMOVED: from edgar import Company, set_identity (Moved inside function)

# Load environment variables (API keys) from the .env file
load_dotenv()

# --- 1. SAFE SETUP (Lazy Loading) ---
def get_openai_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_tavily_client():
    return TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

def configure_gemini():
    if os.getenv("GOOGLE_API_KEY"):
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# REMOVED: SEC Identity setup here. It will be done inside the function.

# --- GLOBAL SYSTEM PROMPT (Single Source of Truth) ---
SYSTEM_PROMPT = """
You are a High-Conviction Investment Analyst managing a "Barbell Strategy" portfolio.
Your mandate is to beat the Nasdaq-100 (QQQ) by identifying Compounders (Alpha) and Momentum Satellites.

When analyzing ANY stock, you must apply the following rigorous framework:

### 1. 🏢 Business & Moat (The "Quality" Check)
- **Business Model:** Summarize what they do.
- **Thesis Check (Pivot):** Has there been "Thesis Drift"? Use `web_search` to validate.
- **Moat:** Does it have high switching costs or Network Effects?

### 2. 📊 The "Beat QQQ" Financial Screen
*Evaluate the stock against these specific benchmarks using `get_financial_metrics`:*
- **Hyper-Growth:** Is `revenue_growth_yoy` > 25%?
- **Efficiency (Rule of 40):** Does `rule_of_40` score exceed 40?
- **Sales Efficiency (Magic Number):** Check `magic_number`.
  - **> 1.0:** Efficient (Invest more).
  - **< 0.7:** **TRAP** (Buying growth inefficiently).
- **Cash Flow Power:** Does OCF cover CapEx? Check if `capex_coverage_percent` > 80%.
- **Shareholder Dilution:** Is `share_count_growth_yoy` < 5%?
- **Margins:** Is `gross_margin` > 70% (Software) or > 50% (Marketplace)?

### 3. Bull & Bear Analysis
- **Bull:** List 3 reasons why the stock is a good investment.
- **Bear:** List 3 reasons why the stock is a bad investment.
- **Competition:** List 3 key competitors and their growth rates.
- **Valuation:** List 3 key valuation metrics and their targets.

### 4. 📉 Technicals & Momentum
- **Trend:** Is `price_above_200dma` True?
- **RSI:** Is `rsi_14_day` < 75?

### 5. 📜 Official Risks
- **SEC Check:** Use `get_sec_filing` for "Risk Factors".
- **Competition:** Name 2 key rivals.

### 6. 🏛️ Final Verdict (The Scorecard)
Present a "Beat QQQ Scorecard" and a definitive action.
**CRITICAL SELL RULES:** You must rate as **SELL** if ANY of the following are true:
1. **Inefficient Growth:** `magic_number` is < 0.7 (The "Growth Trap").
2. **Cash Burn:** `capex_coverage_percent` is < 80% (unless <2yr post-IPO).
3. **Dilution Spiral:** `share_count_growth_yoy` is > 5%.
4. **Fails Rule of 40** AND Revenue Growth is slowing.

Otherwise:
- **STRONG BUY:** Growth > 25%, Rule of 40, Magic Number > 1.0, and PEG < 2.0.
- **HOLD:** Good company but expensive or mixed metrics.
"""

# --- 2. TOOL FUNCTIONS ---

def get_sec_filing(ticker: str):
    """
    Smart fetcher for 10-K/10-Q (US) or 20-F/6-K (Foreign) filings.
    Uses Lazy Loading for 'edgar' to prevent startup crashes.
    """
    print(f"📄 Fetching SEC/Foreign filing for: {ticker}")
    try:
        # --- LAZY IMPORT (The Fix) ---
        from edgar import Company, set_identity
        
        # Initialize Identity just in time
        if os.getenv("SEC_IDENTITY"):
            set_identity(os.getenv("SEC_IDENTITY"))
        # -----------------------------

        company = Company(ticker)
        
        filings = company.get_filings(form=["10-K", "20-F"])
        latest_annual = filings.latest() if filings else None
        
        quarterly_filings = company.get_filings(form=["10-Q", "6-K"])
        latest_update = quarterly_filings.latest() if quarterly_filings else None
        
        doc_text = ""
        source_used = "None"
        
        if latest_update and latest_annual:
            if latest_update.filing_date > latest_annual.filing_date:
                doc_text = latest_update.text()
                source_used = f"{latest_update.form} ({latest_update.filing_date})"
            else:
                doc_text = latest_annual.text()
                source_used = f"{latest_annual.form} ({latest_annual.filing_date})"
        elif latest_annual:
            doc_text = latest_annual.text()
            source_used = f"{latest_annual.form} ({latest_annual.filing_date})"
        elif latest_update:
            doc_text = latest_update.text()
            source_used = f"{latest_update.form} ({latest_update.filing_date})"
            
        if not doc_text:
            return "No recent SEC filings found."

        return f"**Source:** {source_used}\n\n**Filing Text:**\n{doc_text[:25000]}..."

    except Exception as e:
        return f"Error fetching filings: {str(e)}"


def get_financial_metrics(ticker: str):
    """
    Fetches Valuation, Growth, Technicals, Sell Signals, 
    AND the SaaS 'Magic Number' (Sales Efficiency).
    """
    print(f"📊 Fetching deep financials & technicals for: {ticker}")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        financials = stock.financials
        quarterly_financials = stock.quarterly_financials
        cashflow = stock.cashflow
        
        # --- 1. Basic Valuation & EPS ---
        fwd_pe = info.get("forwardPE")
        peg = info.get("pegRatio")
        
        if peg is None and fwd_pe:
            growth_est = info.get("earningsGrowth", 0)
            if growth_est > 0:
                peg = round(fwd_pe / (growth_est * 100), 2)
        
        # --- 2. Advanced Metrics ---
        revenue_cagr_3yr = "N/A"
        ocf_cagr_3yr = "N/A"
        capex_coverage = "N/A"
        share_count_growth = "N/A"
        sbc_percent = "N/A"
        magic_number = "N/A"

        try:
            # A. SaaS Magic Number
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

            # B. Revenue CAGR
            if "Total Revenue" in financials.index:
                revs = financials.loc["Total Revenue"]
                if len(revs) >= 4:
                    curr = revs.iloc[0]
                    past = revs.iloc[3]
                    if past > 0:
                        revenue_cagr_3yr = round(((curr / past) ** (1/3) - 1) * 100, 2)

            # C. OCF & CapEx Coverage
            ocf_val = 0
            capex_val = 0
            
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

            # E. SBC %
            sbc_row = next((idx for idx in cashflow.index if "Stock" in str(idx) and "Compensation" in str(idx)), None)
            if sbc_row and info.get("totalRevenue"):
                sbc_val = cashflow.loc[sbc_row].iloc[0]
                sbc_percent = round((sbc_val / info.get("totalRevenue")) * 100, 2)

        except Exception as e:
            print(f"Warning on advanced metrics: {e}")

        # --- 3. Technicals & Rule of 40 ---
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

        # --- Payload ---
        data = {
            "ticker": ticker.upper(),
            "price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "forward_pe": fwd_pe,
            "peg_ratio": peg,
            "magic_number": magic_number,
            "revenue_growth_yoy": round(rev_growth * 100, 2) if rev_growth else "N/A",
            "revenue_cagr_3yr": revenue_cagr_3yr,
            "capex_coverage_percent": capex_coverage,
            "share_count_growth_yoy": share_count_growth,
            "sbc_percent_revenue": sbc_percent,
            "rule_of_40": rule_of_40,
            "price_above_200dma": price_above_200dma,
            "rsi_14_day": rsi_14,
            "gross_margin": round(info.get("grossMargins", 0) * 100, 2),
            "net_cash": (info.get("totalCash", 0) or 0) - (info.get("totalDebt", 0) or 0),
            "business_summary": info.get("longBusinessSummary")
        }
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": str(e)})

def web_search(query: str):
    """
    Searches the web for recent news using Tavily.
    """
    print(f"🔍 Searching: {query}")
    try:
        # Initialize client here (Lazy Load)
        tavily = get_tavily_client()
        results = tavily.search(query=query, topic="news", search_depth="advanced")
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- 3. OPENAI LOGIC (The "Manual" Loop) ---

TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search for news and analyst ratings.",
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
            "description": "Get price, PEG ratio, and growth metrics.",
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
            "description": "Get the latest SEC 10-K/10-Q/20-F filing text.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]
            }
        }
    }
]

def run_openai_logic(messages):
    """
    Executes the 'manual' function calling loop for OpenAI.
    """
    # Initialize client here (Lazy Load)
    client = get_openai_client()
    
    # 1. First Call: Ask GPT-4o what to do
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS_OPENAI
    )
    
    assistant_msg = response.choices[0].message
    found_tickers = []

    # 2. Check if GPT wants to use a tool
    if assistant_msg.tool_calls:
        messages.append(assistant_msg) # Add the "intent" to history
        
        # Loop through all requested tools
        for tool in assistant_msg.tool_calls:
            args = json.loads(tool.function.arguments)
            func_name = tool.function.name
            result = ""
            
            # Execute the matching Python function locally
            if func_name == "web_search":
                result = web_search(args["query"])
            elif func_name == "get_financial_metrics":
                ticker = args["ticker"]
                found_tickers.append(ticker)
                result = get_financial_metrics(ticker)
            elif func_name == "get_sec_filing":
                ticker = args["ticker"]
                result = get_sec_filing(ticker)
            
            # Feed result back to GPT as a 'tool' message
            messages.append({
                "role": "tool",
                "tool_call_id": tool.id,
                "name": func_name,
                "content": result
            })
            
        # 3. Second Call: GPT generates the final answer with the tool data
        final_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        return final_response.choices[0].message.content, found_tickers
        
    return assistant_msg.content, found_tickers

# --- 4. GEMINI LOGIC (The "Automatic" Loop) ---

def run_gemini_logic(messages, model_name="gemini-2.5-flash"):
    chat_history = []
    
    # Configure Gemini here (Lazy Load)
    configure_gemini()
    
    # Updated Instruction for Deep Analysis
    system_instruction = SYSTEM_PROMPT
    
    # Convert OpenAI message format to Gemini format
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            system_instruction = content
        elif role == "user":
            chat_history.append({"role": "user", "parts": [content]})
        elif role == "assistant" and content:
            chat_history.append({"role": "model", "parts": [content]})
    
    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            # Pass the updated tools list (actual functions, not schema)
            tools=[web_search, get_financial_metrics, get_sec_filing],
            system_instruction=system_instruction
        )
        
        last_user_msg = "Proceed."
        if chat_history and chat_history[-1]["role"] == "user":
            last_user_msg = chat_history.pop()["parts"][0]
            
        # Enable automatic function calling: Google SDK runs the tool loop for us.
        chat = model.start_chat(history=chat_history, enable_automatic_function_calling=True)
        response = chat.send_message(last_user_msg)
        return response.text, []
        
    except Exception as e:
        return f"❌ Error: {str(e)}", []

# --- HELPER: List Available Models ---
def get_valid_gemini_models():
    """
    Returns the best hardcoded options available in your environment.
    """
    return [
        "gemini-3-pro-preview", 
        "deep-research-pro-preview-12-2025", 
        "gemini-2.5-flash"
    ]

# --- 5. MAIN ROUTER ---
def run_smart_agent(messages, model_choice="gpt-4o"):
    if "gemini" in model_choice.lower():
        return run_gemini_logic(messages, model_choice)
    else:
        return run_openai_logic(messages)