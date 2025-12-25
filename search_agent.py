import os
import json
import yfinance as yf
from openai import OpenAI
from tavily import TavilyClient
import google.generativeai as genai
from google.api_core.exceptions import NotFound, PermissionDenied, InvalidArgument
from dotenv import load_dotenv

load_dotenv()

# --- 1. SETUP CLIENTS ---
openai_client = OpenAI()
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# Configure Gemini with a check
if os.getenv("GOOGLE_API_KEY"):
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# --- HELPER: List Available Models (Debug) ---
def get_valid_gemini_models():
    """Returns a list of models available to this API Key."""
    try:
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # Strip 'models/' prefix for cleaner UI
                name = m.name.replace("models/", "")
                models.append(name)
        return models
    except Exception as e:
        print(f"Error listing Gemini models: {e}")
        return ["gemini-1.5-flash", "gemini-pro"] # Fallback defaults

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
    """Fetches metrics + Mission. Auto-calculates PEG."""
    print(f"📊 Fetching deep data for: {ticker}")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        pe_ratio = info.get("trailingPE")
        rev_growth = info.get("revenueGrowth")
        peg_ratio = info.get("pegRatio")
        
        if peg_ratio is None and pe_ratio is not None and rev_growth is not None:
            try:
                growth_rate = rev_growth * 100
                if growth_rate > 0:
                    peg_ratio = round(pe_ratio / growth_rate, 2)
            except:
                peg_ratio = "N/A"

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

# --- 3. OPENAI LOGIC ---
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

# --- 4. GEMINI LOGIC (Updated) ---
def run_gemini_logic(messages, model_name="gemini-1.5-flash"):
    chat_history = []
    system_instruction = "You are a helpful financial analyst."
    
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
            tools=[web_search, get_financial_metrics],
            system_instruction=system_instruction
        )
        
        last_user_msg = "Proceed."
        if chat_history and chat_history[-1]["role"] == "user":
            last_user_msg = chat_history.pop()["parts"][0]
            
        chat = model.start_chat(history=chat_history)
        response = chat.send_message(last_user_msg)
        return response.text, []
        
    except NotFound:
        return f"❌ Error: Model '{model_name}' not found. Try 'gemini-1.5-flash-001' or check your API key permissions.", []
    except InvalidArgument as e:
         return f"❌ Error: Invalid Argument. {str(e)}", []
    except Exception as e:
        return f"❌ Gemini Error: {str(e)}", []

# --- 5. MAIN ROUTER ---
def run_smart_agent(messages, model_choice="gpt-4o"):
    if "gemini" in model_choice.lower():
        return run_gemini_logic(messages, model_choice)
    else:
        return run_openai_logic(messages)