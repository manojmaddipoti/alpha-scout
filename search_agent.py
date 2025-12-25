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

# SEC Identity (Required)
if os.getenv("SEC_IDENTITY"):
    set_identity(os.getenv("SEC_IDENTITY"))

# --- HELPER: List Available Models ---
def get_valid_gemini_models():
    try:
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name.replace("models/", "")
                models.append(name)
        if not models:
            return ["gemini-1.5-flash", "gemini-2.0-flash-exp"]
        return models
    except:
        return ["gemini-1.5-flash"]

# --- 2. TOOL FUNCTIONS ---

def get_10k_filing(ticker: str):
    """
    Fetches the latest 10-K or 10-Q filing from SEC EDGAR.
    Returns the 'Business' and 'Management Discussion' sections.
    """
    print(f"📄 Fetching SEC filing for: {ticker}")
    try:
        # Initialize Company
        company = Company(ticker)
        
        # Try to get 10-K first, then 10-Q
        filings = company.get_filings(form="10-K")
        if not filings:
            filings = company.get_filings(form="10-Q")
        
        if not filings:
            return "No recent 10-K or 10-Q filings found."
            
        latest_filing = filings.latest()
        
        # Basic Info
        info = f"**Filing Type:** {latest_filing.form}\n**Date:** {latest_filing.filing_date}\n\n"
        
        # Extract Text (Chunking to avoid token limits)
        # We grab the full text but usually the AI only needs the first 15k chars 
        # for a quick summary, or specific sections if parsed.
        # simpler approach: get the text object which cleans HTML
        full_text = latest_filing.text()
        
        # Return the first 20,000 characters (approx 5,000 tokens)
        # This covers Item 1 (Business) usually.
        return info + full_text[:20000] + "\n\n...(text truncated for length)..."
        
    except Exception as e:
        return f"Error fetching SEC filing: {str(e)}"

def web_search(query: str):
    print(f"🔍 Searching: {query}")
    try:
        results = tavily.search(query=query, search_depth="advanced")
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})

def get_financial_metrics(ticker: str):
    print(f"📊 Fetching deep data for: {ticker}")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # ... (Keep your existing PEG calculation logic here) ...
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
            "name": "get_10k_filing",
            "description": "Get the latest SEC 10-K/10-Q filing text (Business Description, Risks).",
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
            elif func_name == "get_10k_filing":
                ticker = args["ticker"]
                result = get_10k_filing(ticker)
            
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

# --- 4. GEMINI LOGIC ---
def run_gemini_logic(messages, model_name="gemini-1.5-flash"):
    chat_history = []
    system_instruction = "You are a financial analyst. Use get_10k_filing to read SEC reports when asked."
    
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
            # ADD THE NEW TOOL HERE
            tools=[web_search, get_financial_metrics, get_10k_filing],
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

# --- 5. ROUTER ---
def run_smart_agent(messages, model_choice="gpt-4o"):
    if "gemini" in model_choice.lower():
        return run_gemini_logic(messages, model_choice)
    else:
        return run_openai_logic(messages)