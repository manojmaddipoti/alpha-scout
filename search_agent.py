import os
import json
import yfinance as yf
from openai import OpenAI
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# --- TOOL 1: Web Search ---
def web_search(query: str):
    """Searches for news, SEC filing summaries, and sentiment."""
    print(f"🔍 Searching: {query}")
    return json.dumps(tavily.search(query=query, search_depth="advanced"))

# --- TOOL 2: Financial Metrics ---
def get_financial_metrics(ticker: str):
    """Fetches valuation metrics using yfinance."""
    print(f"📊 Fetching data for: {ticker}")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # safely get data with defaults
        data = {
            "ticker": ticker.upper(), # Return ticker so UI knows what we found
            "price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "revenue": info.get("totalRevenue"),
            "gross_profit": info.get("grossProfits"),
            "free_cash_flow": info.get("freeCashflow"),
            "debt_to_equity": info.get("debtToEquity"),
            "target_price": info.get("targetMeanPrice")
        }
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": str(e)})

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Finds news, SEC 10-K/10-Q summaries, and market sentiment.",
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
            "description": "Get valuation metrics for a stock. Agent MUST convert Company Name to Ticker (e.g., 'Sea Limited' -> 'SE').",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "The stock symbol (e.g. SE, NVDA)"}},
                "required": ["ticker"]
            }
        }
    }
]

def run_smart_agent(messages):
    """
    Returns TWO things: 
    1. The text response
    2. A list of tickers the agent decided to use (for the UI to chart)
    """
    
    # First call
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS
    )
    
    assistant_msg = response.choices[0].message
    found_tickers = [] # Store tickers found by the agent

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
                found_tickers.append(ticker) # <--- CAPTURE THE TICKER
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