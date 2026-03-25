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

# Tool Functions

def get_sec_filing(ticker: str):
    """Fetch latest SEC filing (10-K/10-Q/20-F/6-K) for a given ticker."""
    try:
        from edgar import Company, set_identity

        sec_identity = os.getenv("SEC_IDENTITY", "Agent user@example.com")
        set_identity(sec_identity)

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
            return f"No recent SEC filings found for {ticker}."

        return f"**Source:** {source_used}\n\n**Filing Text:**\n{doc_text[:25000]}..."

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
            ocf_val = 0
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
                if sbc_row and info.get("totalRevenue"):
                    sbc_val = cashflow.loc[sbc_row].iloc[0]
                    sbc_percent = round((sbc_val / info.get("totalRevenue")) * 100, 2)

        except Exception:
            pass

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

        # Compile Results
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
            "gross_margin": round(info.get("grossMargins", 0) * 100, 2) if info.get("grossMargins") else "N/A",
            "net_cash": (info.get("totalCash", 0) or 0) - (info.get("totalDebt", 0) or 0),
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
                        "description": "Search for news and analyst ratings.",
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
                        "description": "Get price, PEG ratio, and growth metrics for a stock ticker.",
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
                        "description": "Get the latest SEC 10-K/10-Q/20-F filing text.",
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
        "description": "Search for news and analyst ratings.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"]
        }
    },
    {
        "name": "get_financial_metrics",
        "description": "Get price, PEG ratio, and growth metrics for a stock ticker.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"]
        }
    },
    {
        "name": "get_sec_filing",
        "description": "Get the latest SEC 10-K/10-Q/20-F filing text.",
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