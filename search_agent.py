import os
import json
import yfinance as yf
from openai import OpenAI
from tavily import TavilyClient
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# --- 1. SETUP CLIENTS ---
openai_client = OpenAI()
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# Configure Gemini
if os.getenv("GOOGLE_API_KEY"):
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# --- 2. TOOL FUNCTIONS ---
def web_search(query: str):
    """Searches for news, analyst sentiment, and Bull/Bear thesis."""
    print(f"🔍 Searching: {query}")
    try:
        results = tavily.search(query=query, search_depth="advanced")
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})

def get_financial_metrics(ticker: str):
    """Fetches metrics + Mission. Auto-calculates PEG if missing."""
    print(f"📊 Fetching deep data for: {ticker}")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        pe_ratio = info.get("trailingPE")
        rev_growth = info.get("revenueGrowth")
        peg_ratio = info.get("pegRatio")
        
        # Calc PEG if missing
        if peg_ratio is None and pe_ratio is not None and rev_growth is not None:
            try:
                growth_rate = rev_growth * 100
                if growth_rate > 0:
                    peg_ratio = round(pe_ratio / growth_rate, 2)
            except:
                peg_ratio = "N/A (Calc Failed)"

        data = {
            "ticker": ticker.upper(),
            "company_name": info.get("longName"),
            "mission": info.get("longBusinessSummary", "Mission not available."),
            "current_price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": pe_ratio,
            "peg_ratio": peg_ratio,
            "revenue_growth": round(rev_growth * 100, 2) if rev_growth else "N/A",
            "gross_margin": round(info.get("grossMargins", 0) * 100, 2),
        }
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": str(e)})

# --- 3. OPENAI SPECIFIC LOGIC ---
TOOLS_OPENAI = [
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

def run_openai_logic(messages):
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS_OPENAI
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
            
        final_response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        return final_response.choices[0].message.content, found_tickers
        
    return assistant_msg.content, found_tickers

# --- 4. GEMINI SPECIFIC LOGIC ---
def run_gemini_logic(messages, model_name="gemini-1.5-flash"):
    """
    Adapts OpenAI message history to Gemini format and runs the agent.
    """
    # Convert History: OpenAI [{"role": "user"}] -> Gemini Content objects
    chat_history = []
    system_instruction = ""
    
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        
        if role == "system":
            system_instruction = content
        elif role == "user":
            chat_history.append({"role": "user", "parts": [content]})
        elif role == "assistant":
            chat_history.append({"role": "model", "parts": [content]})
    
    # Initialize Model with Tools (Gemini handles the loop automatically!)
    model = genai.GenerativeModel(
        model_name=model_name,
        tools=[web_search, get_financial_metrics],
        system_instruction=system_instruction
    )
    
    # Start Chat
    chat = model.start_chat(history=chat_history)
    
    # Send latest message (which is usually the last user prompt)
    # We need to extract the LAST user message to send as the trigger
    last_msg = chat_history[-1]["parts"][0]
    
    # Note: We need to pop the last message from history so we don't duplicate it in start_chat + send_message
    # But for simplicity in this bridge, we assume the 'messages' list is full history.
    # A cleaner way with Gemini is to just send the prompt to a fresh chat if history is maintained externally.
    
    response = chat.send_message(last_msg)
    
    # Check for tickers in function calls (for the chart)
    found_tickers = []
    # Gemini SDK doesn't make it easy to inspect intermediate tool calls in 'automatic' mode easily
    # So we will try to extract ticker from the text response or valid parts
    # (Simplified for now: We might miss the chart update on Gemini, but the text will work)
    
    return response.text, found_tickers

# --- 5. MAIN ROUTER ---
def run_smart_agent(messages, model_choice="gpt-4o"):
    if "gemini" in model_choice.lower():
        return run_gemini_logic(messages, model_choice)
    else:
        return run_openai_logic(messages)