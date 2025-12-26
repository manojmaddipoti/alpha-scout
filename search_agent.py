import os
import json
import yfinance as yf
import pandas as pd
from openai import OpenAI
from tavily import TavilyClient
import google.generativeai as genai
from google.api_core.exceptions import NotFound, InvalidArgument
from dotenv import load_dotenv
from edgar import Company, set_identity

# Load environment variables (API keys) from the .env file
load_dotenv()

# --- 1. SETUP CLIENTS ---
# Initialize OpenAI client. It looks for 'OPENAI_API_KEY' in environment variables automatically.
openai_client = OpenAI()

# Initialize Tavily client for web searching. Requires 'TAVILY_API_KEY'.
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# Configure Google Generative AI (Gemini) if the key exists.
if os.getenv("GOOGLE_API_KEY"):
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Set SEC Identity. This is MANDATORY to prevent the SEC from blocking your IP.
# Format: "Name email@domain.com"
if os.getenv("SEC_IDENTITY"):
    set_identity(os.getenv("SEC_IDENTITY"))

# --- GLOBAL SYSTEM PROMPT (Single Source of Truth) ---
SYSTEM_PROMPT = """
You are a High-Conviction Investment Analyst managing a "Barbell Strategy" portfolio.
Your mandate is to beat the Nasdaq-100 (QQQ) by identifying two types of assets:
1. **Compounders (Alpha):** High-growth stocks (>25% growth) with efficient unit economics.
2. **Momentum Satellites:** Stocks showing relative strength and technical breakouts.

When analyzing ANY stock, you must apply the following rigorous framework using the provided tools:

### 1. 🏢 Business & Moat (The "Quality" Check)
- **Business Model:** Summarize what they do. Is it a Platform/Ecosystem or a Point Solution?
- **Thesis Check (Pivot):** Has there been "Thesis Drift" or a strategic pivot (e.g., Crypto miner shifting to AI Cloud)? Use `web_search` to validate recent news vs. old 10-K data.
- **Moat:** Does it have high switching costs (Sticky) or Network Effects?

### 2. 📊 The "Beat QQQ" Financial Screen
*Evaluate the stock against these specific benchmarks using `get_financial_metrics`:*
- **Hyper-Growth:** Is `revenue_growth_yoy` > 25%? (Crucial for beating QQQ).
- **Efficiency (Rule of 40):** Does the calculated `rule_of_40` score exceed 40?
- **Shareholder Respect:** Is Stock-Based Compensation (`sbc_percent_revenue`) < 20% of Revenue?
- **Stickiness (NRR):** Use `web_search` to find "Net Revenue Retention" or "NRR". Is it > 115%? (If unavailable, mark "Unknown").
- **Margins:** Is `gross_margin` > 70% (Software) or > 50% (Marketplace)?

### 3. 📉 Technicals & Momentum (Timing)
*Use the technical data provided in `get_financial_metrics`:*
- **Trend Filter:** Is `price_above_200dma` equal to `True`? (Bullish Signal).
- **Oscillator:** Is `rsi_14_day` between 50-70 (Healthy) or >75 (Overbought)?
- **Relative Strength:** Use `web_search` to check "Stock performance vs QQQ last 6 months".

### 4. 📜 Official Risks (The Bear Case)
- **SEC Check:** Use `get_sec_filing` to read the "Risk Factors". Highlight the #1 specific operational risk (not generic boilerplate).
- **Competition:** Name 2 key rivals. Are they growing faster or slower?

### 5. ⚖️ Valuation (The Price Tag)
- **The Metric that Matters:** Focus on the **PEG Ratio (Forward)**.
  - *Target:* PEG < 1.5 is Cheap; PEG > 2.0 is Expensive.
- **Cash Runway:** Look at `net_cash`. Does the balance sheet support the burn rate?

### 6. 🏛️ Final Verdict (The Scorecard)
Present a summary "Beat QQQ Scorecard" (e.g., "Score: 4/5") and a definitive action:
- **STRONG BUY:** Passes Growth (>25%), Rule of 40, and PEG < 2.0. (High Conviction).
- **MOMENTUM BUY:** Fundamentals are mixed, but Price is > 200DMA and RSI is rising. (Satellite Trade).
- **HOLD:** Good company but growing < 20% or Valuation is too high (PEG > 2.5).
- **SELL:** Fails Rule of 40, Thesis Drift, or Revenue Deceleration without Profitability.
"""

# --- 2. TOOL FUNCTIONS (The "Upgraded" versions) ---
# These functions act as the "tools" the AI can use to fetch external data.

def get_sec_filing(ticker: str):
    """
    Smart fetcher for 10-K/10-Q (US) or 20-F/6-K (Foreign) filings.
    It compares dates to prioritize the absolute latest strategic update.
    """
    print(f"📄 Fetching SEC/Foreign filing for: {ticker}")
    try:
        company = Company(ticker)
        
        # 1. Strategy: Try to find the most recent "Annual" report first
        # US companies file 10-K; Foreign Private Issuers file 20-F.
        filings = company.get_filings(form=["10-K", "20-F"])
        latest_annual = filings.latest() if filings else None
        
        # 2. Check for very recent Quarterly/Material updates (10-Q or 6-K)
        # Foreign companies use 6-K for earnings and major announcements between annual reports.
        quarterly_filings = company.get_filings(form=["10-Q", "6-K"])
        latest_update = quarterly_filings.latest() if quarterly_filings else None
        
        doc_text = ""
        source_used = "None"
        
        # Decision Logic: If the 6-K/10-Q is newer than the Annual, use IT for the pivot news.
        # This helps catch recent strategy shifts (like "Bitcoin -> AI") that aren't in last year's 10-K.
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

        # Return the Source + First 25k chars.
        # 25k chars is usually enough to capture "Item 1. Business" and "Item 1A. Risk Factors".
        return f"**Source:** {source_used}\n\n**Filing Text:**\n{doc_text[:25000]}..."

    except Exception as e:
        return f"Error fetching filings: {str(e)}"


def get_financial_metrics(ticker: str):
    """
    Fetches Price, Valuation, Cash Flow, Rule of 40, CAGRs, 
    AND Technicals (RSI, 200-SMA) + SBC Analysis.
    """
    print(f"📊 Fetching deep financials & technicals for: {ticker}")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # --- 1. Basic Valuation & EPS ---
        fwd_pe = info.get("forwardPE")
        peg = info.get("pegRatio")
        trailing_eps = info.get("trailingEps")
        forward_eps = info.get("forwardEps")
        
        # Fallback PEG Calculation
        if peg is None and fwd_pe:
            growth_est = info.get("earningsGrowth", 0)
            if growth_est > 0:
                peg = round(fwd_pe / (growth_est * 100), 2)
        
        # --- 2. Advanced Financials (SBC & CAGRs) ---
        financials = stock.financials
        cashflow = stock.cashflow
        
        # A. Stock-Based Compensation (SBC) as % of Revenue
        sbc_value = 0
        sbc_percent = "N/A"
        try:
            # Look for SBC in Cash Flow Statement
            if "Stock Based Compensation" in cashflow.index:
                sbc_value = cashflow.loc["Stock Based Compensation"].iloc[0]
            elif "Share Based Compensation" in cashflow.index:
                sbc_value = cashflow.loc["Share Based Compensation"].iloc[0]
            
            total_revenue = info.get("totalRevenue")
            if total_revenue and sbc_value:
                # SBC is often a positive add-back in CF, but represents a cost. 
                # We want the ratio: SBC / Revenue
                sbc_percent = round((sbc_value / total_revenue) * 100, 2)
        except Exception:
            pass

        # B. Revenue & OCF CAGR (3-Year)
        revenue_cagr_3yr = "N/A"
        ocf_cagr_3yr = "N/A"
        
        try:
            if "Total Revenue" in financials.index:
                revenues = financials.loc["Total Revenue"]
                if len(revenues) >= 4:
                    curr_rev = revenues.iloc[0]
                    past_rev = revenues.iloc[3]
                    if past_rev > 0:
                        revenue_cagr_3yr = round(((curr_rev / past_rev) ** (1/3) - 1) * 100, 2)
            
            # Find OCF row safely
            ocf_row = next((idx for idx in cashflow.index if "Operating" in str(idx) and "Cash" in str(idx)), None)
            if ocf_row:
                ocfs = cashflow.loc[ocf_row]
                if len(ocfs) >= 4:
                    curr_ocf = ocfs.iloc[0]
                    past_ocf = ocfs.iloc[3]
                    if past_ocf > 0 and curr_ocf > 0:
                        ocf_cagr_3yr = round(((curr_ocf / past_ocf) ** (1/3) - 1) * 100, 2)
        except Exception:
            pass

        # --- 3. Technical Analysis (RSI & 200-SMA) ---
        # We need historical price data for this
        history = stock.history(period="1y") # 1 year of data
        price_above_200dma = "N/A"
        rsi_14 = "N/A"
        
        if not history.empty and len(history) > 200:
            # 200-Day Moving Average
            sma_200 = history["Close"].rolling(window=200).mean().iloc[-1]
            current_price = history["Close"].iloc[-1]
            price_above_200dma = True if current_price > sma_200 else False
            
            # RSI (14-Day)
            delta = history["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_14 = round(100 - (100 / (1 + rs.iloc[-1])), 2)

        # --- 4. Rule of 40 Calculation ---
        rule_of_40 = "N/A"
        rev_growth = info.get("revenueGrowth", 0)
        fcf_margin = 0
        
        if info.get("totalRevenue") and info.get("freeCashflow"):
            fcf_margin = info.get("freeCashflow") / info.get("totalRevenue")
        else:
            fcf_margin = info.get("ebitdaMargins", 0)

        if rev_growth is not None:
            rule_of_40 = round((rev_growth * 100) + (fcf_margin * 100), 2)

        # --- 5. Return Data Payload ---
        data = {
            "ticker": ticker.upper(),
            "price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "forward_pe": fwd_pe,
            "peg_ratio": peg,
            "sbc_percent_revenue": sbc_percent,  # <--- NEW
            "price_above_200dma": price_above_200dma, # <--- NEW
            "rsi_14_day": rsi_14, # <--- NEW
            "revenue_growth_yoy": round(rev_growth * 100, 2) if rev_growth else "N/A",
            "revenue_cagr_3yr": revenue_cagr_3yr,
            "rule_of_40": rule_of_40,
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
    Topic is set to 'news' to filter out generic blog spam.
    """
    print(f"🔍 Searching: {query}")
    try:
        results = tavily.search(query=query, topic="news", search_depth="advanced")
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- 3. OPENAI LOGIC (The "Manual" Loop) ---
# OpenAI requires us to manually define the tool schema and handle the tool execution loop.

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
    1. Send Prompt -> 2. AI requests Tool -> 3. We run Tool -> 4. Send Tool Output -> 5. AI answers.
    """
    # 1. First Call: Ask GPT-4o what to do
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS_OPENAI
    )
    
    assistant_msg = response.choices[0].message
    found_tickers = []

    # 2. Check if GPT wants to use a tool
    if assistant_msg.tool_calls:
        messages.append(assistant_msg) # Add the "intent" to history
        
        # Loop through all requested tools (it might ask for multiple)
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
        final_response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        return final_response.choices[0].message.content, found_tickers
        
    return assistant_msg.content, found_tickers

# --- 4. GEMINI LOGIC (The "Automatic" Loop) ---
# Gemini SDK handles the tool execution loop automatically if we pass the functions directly.

def run_gemini_logic(messages, model_name="gemini-2.5-flash"):
    chat_history = []
    
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
    Fetches available Gemini models.
    Returns the best hardcoded options if the dynamic fetch fails.
    """
    try:
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name.replace("models/", "")
                models.append(name)
        if not models:
            # FALLBACK: These are the exact strings you need
            return ["gemini-1.5-pro", "gemini-2.0-flash-exp", "gemini-1.5-flash"]
        return models
    except Exception:
        return ["gemini-1.5-pro", "gemini-2.0-flash-exp", "gemini-1.5-flash"]

# --- 5. MAIN ROUTER ---
# Decides which logic to run based on the user's selection in the UI.
def run_smart_agent(messages, model_choice="gpt-4o"):
    if "gemini" in model_choice.lower():
        return run_gemini_logic(messages, model_choice)
    else:
        # This calls the OpenAI logic defined above
        return run_openai_logic(messages)