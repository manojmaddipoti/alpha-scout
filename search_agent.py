import os
import json
import yfinance as yf
from openai import OpenAI
from tavily import TavilyClient
import google.generativeai as genai
from google.api_core.exceptions import NotFound, InvalidArgument
from dotenv import load_dotenv
from edgar import Company, set_identity

load_dotenv()

# --- 1. SETUP CLIENTS ---
openai_client = OpenAI()
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

if os.getenv("GOOGLE_API_KEY"):
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

if os.getenv("SEC_IDENTITY"):
    set_identity(os.getenv("SEC_IDENTITY"))

# --- 2. TOOL FUNCTIONS (The "Upgraded" versions) ---

def get_sec_filing(ticker: str):
    """
    Smart fetcher for 10-K/10-Q (US) or 20-F/6-K (Foreign) filings.
    Prioritizes the absolute latest strategic update.
    """
    print(f"📄 Fetching SEC/Foreign filing for: {ticker}")
    try:
        company = Company(ticker)
        
        # 1. Strategy: Try to find the most recent "Annual" report first
        filings = company.get_filings(form=["10-K", "20-F"])
        latest_annual = filings.latest() if filings else None
        
        # 2. Check for very recent Quarterly/Material updates (10-Q or 6-K)
        quarterly_filings = company.get_filings(form=["10-Q", "6-K"])
        latest_update = quarterly_filings.latest() if quarterly_filings else None
        
        doc_text = ""
        source_used = "None"
        
        # Decision Logic: If update is newer than annual, use it
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
    Fetches Price, Valuation, Cash Flow, Rule of 40, and 3-Year CAGRs 
    (Revenue & Operating Cash Flow).
    """
    print(f"📊 Fetching deep financials for: {ticker}")
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
        
        # --- 2. Advanced Growth Metrics (CAGRs) ---
        revenue_cagr_3yr = "N/A"
        ocf_cagr_3yr = "N/A"
        gross_profit = info.get("grossProfits", "N/A")
        operating_cf = info.get("operatingCashflow", "N/A")

        try:
            # We need historical data for CAGR
            financials = stock.financials  # Income Statement
            cashflow = stock.cashflow      # Cash Flow Statement
            
            # A. Revenue CAGR (3-Year)
            if "Total Revenue" in financials.index:
                revenues = financials.loc["Total Revenue"]
                if len(revenues) >= 4:
                    curr_rev = revenues.iloc[0]
                    past_rev = revenues.iloc[3] # 3 years ago
                    if past_rev > 0:
                        cagr = (curr_rev / past_rev) ** (1/3) - 1
                        revenue_cagr_3yr = round(cagr * 100, 2)

            # B. Operating Cash Flow CAGR (3-Year)
            # Row name varies: usually "Operating Cash Flow" or "Total Cash From Operating Activities"
            # We search for the row that contains "Operating"
            ocf_row = None
            for idx in cashflow.index:
                if "Operating" in str(idx) and "Cash" in str(idx):
                    ocf_row = idx
                    break
            
            if ocf_row:
                ocfs = cashflow.loc[ocf_row]
                if len(ocfs) >= 4:
                    curr_ocf = ocfs.iloc[0]
                    past_ocf = ocfs.iloc[3]
                    # CAGR math fails if starting value is negative
                    if past_ocf > 0 and curr_ocf > 0:
                        cagr_ocf = (curr_ocf / past_ocf) ** (1/3) - 1
                        ocf_cagr_3yr = round(cagr_ocf * 100, 2)
                    elif past_ocf < 0:
                        ocf_cagr_3yr = "N/A (Neg Start)"

            # Fallback for Gross Profit
            if gross_profit == "N/A" and "Gross Profit" in financials.index:
                gross_profit = financials.loc["Gross Profit"].iloc[0]

        except Exception as e:
            print(f"Warning: Could not calculate CAGR: {e}")

        # --- 3. Rule of 40 Calculation ---
        rule_of_40 = "N/A"
        rev_growth = info.get("revenueGrowth", 0)
        
        # FCF Margin
        total_revenue = info.get("totalRevenue")
        free_cash_flow = info.get("freeCashflow")
        
        fcf_margin = 0
        if total_revenue and free_cash_flow:
            fcf_margin = free_cash_flow / total_revenue
        else:
            fcf_margin = info.get("ebitdaMargins", 0)

        if rev_growth is not None:
            score = (rev_growth * 100) + (fcf_margin * 100)
            rule_of_40 = round(score, 2)

        # --- 4. Return Data Payload ---
        data = {
            "ticker": ticker.upper(),
            "price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "forward_pe": fwd_pe,
            "peg_ratio": peg,
            "trailing_eps": trailing_eps,
            "forward_eps": forward_eps,
            "revenue_growth_yoy": round(rev_growth * 100, 2) if rev_growth else "N/A",
            "revenue_cagr_3yr": revenue_cagr_3yr,
            "operating_cash_flow": operating_cf,
            "ocf_cagr_3yr": ocf_cagr_3yr,
            "gross_profit": gross_profit,
            "gross_margin": round(info.get("grossMargins", 0) * 100, 2),
            "rule_of_40": rule_of_40,
            "total_cash": info.get("totalCash"),
            "total_debt": info.get("totalDebt"),
            "net_cash": (info.get("totalCash", 0) or 0) - (info.get("totalDebt", 0) or 0),
            "free_cash_flow": free_cash_flow,
            "business_summary": info.get("longBusinessSummary")
        }
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": str(e)})

def web_search(query: str):
    print(f"🔍 Searching: {query}")
    try:
        results = tavily.search(query=query, topic="news", search_depth="advanced")
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- 3. OPENAI LOGIC (The "Manual" Loop) ---
# We define the schema to match the tool functions above exactly.
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
        
        # Loop through all requested tools
        for tool in assistant_msg.tool_calls:
            args = json.loads(tool.function.arguments)
            func_name = tool.function.name
            result = ""
            
            # Execute the matching Python function
            if func_name == "web_search":
                result = web_search(args["query"])
            elif func_name == "get_financial_metrics":
                ticker = args["ticker"]
                found_tickers.append(ticker)
                result = get_financial_metrics(ticker)
            elif func_name == "get_sec_filing":
                ticker = args["ticker"]
                result = get_sec_filing(ticker)
            
            # Feed result back to GPT
            messages.append({
                "role": "tool",
                "tool_call_id": tool.id,
                "name": func_name,
                "content": result
            })
            
        # 3. Second Call: GPT generates the final answer
        final_response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        return final_response.choices[0].message.content, found_tickers
        
    return assistant_msg.content, found_tickers

# --- 4. GEMINI LOGIC (The "Automatic" Loop) ---
def run_gemini_logic(messages, model_name="gemini-2.5-flash"):
    chat_history = []
    
    # Updated Instruction for Deep Analysis
    system_instruction = """
    You are a Hedge Fund Analyst. 
    1. **Strategic Pivot Check:** Check if the company is shifting business models (e.g., Crypto to AI). Trust recent 6-K/8-K or News over old Annual Reports.
    2. **CapEx Analysis:** For infrastructure stocks (AI/Miners), compare Market Cap to Cash/Debt. Are they burning cash to build?
    3. **Valuation:** Use Forward P/E and PEG.
    4. Always use `get_sec_filing` for "Risk Factors".
    """
    
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
            # Pass the updated tools list
            tools=[web_search, get_financial_metrics, get_sec_filing],
            system_instruction=system_instruction
        )
        
        last_user_msg = "Proceed."
        if chat_history and chat_history[-1]["role"] == "user":
            last_user_msg = chat_history.pop()["parts"][0]
            
        chat = model.start_chat(history=chat_history, enable_automatic_function_calling=True)
        response = chat.send_message(last_user_msg)
        return response.text, []
        
    except Exception as e:
        return f"❌ Error: {str(e)}", []
# --- HELPER: List Available Models ---
def get_valid_gemini_models():
    """
    Fetches available Gemini models that support content generation.
    Falls back to a default list if the API fails.
    """
    try:
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name.replace("models/", "")
                models.append(name)
        if not models:
            return ["gemini-1.5-flash", "gemini-2.0-flash-exp","gemini-2.5-flash"]
        return models
    except Exception:
        # Fallback if API key is invalid or network fails
        return ["gemini-1.5-flash", "gemini-2.0-flash-exp","gemini-2.5-flash"]

# --- 5. MAIN ROUTER ---
def run_smart_agent(messages, model_choice="gpt-4o"):
    if "gemini" in model_choice.lower():
        return run_gemini_logic(messages, model_choice)
    else:
        # Now this works because run_openai_logic is defined above!
        return run_openai_logic(messages)