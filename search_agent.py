import os
import json
import yfinance as yf
from openai import OpenAI
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

def web_search(query: str):
    """Searches for news, analyst sentiment, and Bull/Bear thesis."""
    print(f"🔍 Searching: {query}")
    return json.dumps(tavily.search(query=query, search_depth="advanced"))

def get_financial_metrics(ticker: str):
    """Fetches metrics + Mission. Auto-calculates PEG if missing."""
    print(f"📊 Fetching deep data for: {ticker}")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # --- 1. Get Base Data ---
        pe_ratio = info.get("trailingPE")
        rev_growth = info.get("revenueGrowth") # e.g. 0.25 for 25%
        
        # --- 2. Smart PEG Calculation ---
        # Try getting it directly first
        peg_ratio = info.get("pegRatio")
        
        # If missing, try to calculate: PEG = (P/E) / (Growth Rate * 100)
        if peg_ratio is None and pe_ratio is not None and rev_growth is not None:
            try:
                growth_rate = rev_growth * 100
                if growth_rate > 0:
                    peg_ratio = round(pe_ratio / growth_rate, 2)
            except:
                peg_ratio = "N/A (Calc Failed)"

        # --- 3. Get Company Mission ---
        mission = info.get("longBusinessSummary", "Mission not available.")

        # --- 4. Compile Data ---
        data = {
            "ticker": ticker.upper(),
            "company_name": info.get("longName"),
            "mission": mission,  # <--- Added Mission
            "current_price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": pe_ratio,
            "peg_ratio": peg_ratio, # <--- Fixed PEG
            "revenue_growth": round(rev_growth * 100, 2) if rev_growth else "N/A",
            "gross_margin": round(info.get("grossMargins", 0) * 100, 2),
            "rule_of_40": "Calculate this from growth + margin",
            "sbc_percent": "Calculate this from Cash Flow / Revenue",
        }
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": str(e)})

# Tools Definition
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search for 'Bull case', 'Bear case', and 'Analyst Ratings'.",
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
            "description": "Get financial data, PEG ratio, and Company Mission.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]
            }
        }
    }
]

def run_smart_agent(messages):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS
    )
    
    assistant_msg = response.choices[0].message
    found_tickers = []

    if assistant_msg.tool_calls:
        messages.append(assistant_msg)
        
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