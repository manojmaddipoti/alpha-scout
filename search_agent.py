import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from google import genai
from openai import OpenAI
from tavily import TavilyClient

from metrics import get_competitor_metrics_json, get_equity_metrics_json
from model_config import CLAUDE_MODEL, GEMINI_MODEL, OPENAI_MODEL

load_dotenv()

PROTOCOL_PATH = Path(__file__).parent / "analysis_protocol.md"
SYSTEM_PROMPT = PROTOCOL_PATH.read_text(encoding="utf-8")
MAX_TOOL_ITERATIONS = 8
MAX_OUTPUT_TOKENS = 12000
WEB_SEARCH_MAX_RESULTS = 5
WEB_SEARCH_CONTENT_TRUNC = 1800
SEC_SECTION_TRUNC = 10000


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


def get_sec_filing(ticker: str):
    """Fetch latest 10-K/10-Q and extract Item 7/MD&A and Item 1A/Risk Factors."""
    try:
        from edgar import Company, set_identity

        sec_identity = os.getenv("SEC_IDENTITY", "Agent user@example.com")
        set_identity(sec_identity)

        company = Company(ticker)
        annual = company.get_filings(form=["10-K", "20-F"])
        latest_annual = annual.latest() if annual else None
        quarterly = company.get_filings(form=["10-Q", "6-K"])
        latest_quarter = quarterly.latest() if quarterly else None

        filing = latest_annual or latest_quarter
        if not filing:
            return f"No recent SEC filings found for {ticker}."

        source_used = f"{filing.form} ({filing.filing_date})"
        mda_text = ""
        risk_text = ""

        try:
            filing_obj = filing.obj()
            for attr in ("management_discussion", "mda", "item_7"):
                if hasattr(filing_obj, attr) and getattr(filing_obj, attr):
                    mda_text = str(getattr(filing_obj, attr))
                    break
            for attr in ("risk_factors", "item_1a"):
                if hasattr(filing_obj, attr) and getattr(filing_obj, attr):
                    risk_text = str(getattr(filing_obj, attr))
                    break
        except Exception:
            pass

        if not mda_text or not risk_text:
            full_text = filing.text()
            if not risk_text:
                m = re.search(
                    r"Item\s*1A\.?\s*Risk\s*Factors(.{500,80000}?)(?=Item\s*1B|Item\s*2\.?\s*Properties)",
                    full_text,
                    re.IGNORECASE | re.DOTALL,
                )
                if m:
                    risk_text = m.group(1).strip()
            if not mda_text:
                m = re.search(
                    r"Item\s*7\.?\s*Management.{0,80}Discussion(.{500,80000}?)(?=Item\s*7A|Item\s*8\.?\s*Financial)",
                    full_text,
                    re.IGNORECASE | re.DOTALL,
                )
                if m:
                    mda_text = m.group(1).strip()

        parts = [f"**Source:** {source_used}"]
        parts.append(
            f"\n**Item 7 / MD&A:**\n{mda_text[:SEC_SECTION_TRUNC]}"
            if mda_text
            else "\n**Item 7 / MD&A:** Could not extract."
        )
        parts.append(
            f"\n**Item 1A / Risk Factors:**\n{risk_text[:SEC_SECTION_TRUNC]}"
            if risk_text
            else "\n**Item 1A / Risk Factors:** Could not extract."
        )
        return "\n".join(parts)
    except Exception as exc:
        return f"Error fetching SEC filings for {ticker}: {exc}"


def get_financial_metrics(ticker: str):
    """Fetch corrected financial metrics with true ROIC and FCF fields."""
    return get_equity_metrics_json(ticker)


def get_competitor_metrics(target_ticker: str, competitors: list[str] | None = None):
    """Fetch a compact competitor matrix for the target and public peers."""
    return get_competitor_metrics_json(target_ticker, competitors)


def web_search(query: str):
    """Search the web for recent news and information using Tavily."""
    try:
        tavily = get_tavily_client()
        results = tavily.search(
            query=query,
            topic="news",
            search_depth="advanced",
            max_results=WEB_SEARCH_MAX_RESULTS,
        )
        for result in results.get("results", []):
            if "content" in result and isinstance(result["content"], str):
                result["content"] = result["content"][:WEB_SEARCH_CONTENT_TRUNC]
            result.pop("raw_content", None)
        return json.dumps(results)
    except Exception as exc:
        return json.dumps({"error": f"Search error: {exc}"})


def _dispatch_tool(name: str, args: dict, found_tickers: list[str]) -> str:
    if name == "web_search":
        return web_search(args["query"])
    if name == "get_financial_metrics":
        ticker = args["ticker"].upper()
        found_tickers.append(ticker)
        return get_financial_metrics(ticker)
    if name == "get_competitor_metrics":
        target = args["target_ticker"].upper()
        competitors = [ticker.upper() for ticker in args.get("competitors", [])]
        found_tickers.extend([target, *competitors])
        return get_competitor_metrics(target, competitors)
    if name == "get_sec_filing":
        ticker = args["ticker"].upper()
        found_tickers.append(ticker)
        return get_sec_filing(ticker)
    return f"Unknown tool: {name}"


TOOL_SPECS = [
    {
        "name": "web_search",
        "description": "Search current news, earnings, competitor context, catalysts, and consensus expectations.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_financial_metrics",
        "description": "Fetch forensic financial metrics for one ticker: true ROIC, ROE, OCF, FCF, FCF yield, SBC/OCF, valuation, consensus, short interest, technicals, sector, and industry.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_competitor_metrics",
        "description": "Fetch a compact competitor matrix for the target plus 3-5 public peer tickers. Use web_search first if the right competitors are not obvious.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_ticker": {"type": "string"},
                "competitors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-5 public competitor tickers.",
                },
            },
            "required": ["target_ticker"],
        },
    },
    {
        "name": "get_sec_filing",
        "description": "Retrieve targeted MD&A and Risk Factors from the latest 10-K/20-F or 10-Q/6-K.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
]


TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["parameters"],
        },
    }
    for tool in TOOL_SPECS
]

TOOLS_CLAUDE = [
    {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["parameters"],
    }
    for tool in TOOL_SPECS
]

TOOLS_GEMINI = [{"function_declarations": TOOL_SPECS}]


def run_openai_logic(messages, model_name=OPENAI_MODEL):
    """Execute OpenAI function calling with a multi-turn tool loop."""
    try:
        client = get_openai_client()
        conversation = [dict(message) for message in messages]
        found_tickers: list[str] = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = client.chat.completions.create(
                model=model_name,
                messages=conversation,
                tools=TOOLS_OPENAI,
                max_completion_tokens=MAX_OUTPUT_TOKENS,
            )
            assistant_msg = response.choices[0].message

            if not assistant_msg.tool_calls:
                return assistant_msg.content or "", sorted(set(found_tickers))

            conversation.append({
                "role": "assistant",
                "content": assistant_msg.content,
                "tool_calls": [tool_call.model_dump() for tool_call in assistant_msg.tool_calls],
            })

            for tool_call in assistant_msg.tool_calls:
                args = json.loads(tool_call.function.arguments or "{}")
                result = _dispatch_tool(tool_call.function.name, args, found_tickers)
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": result,
                })

        return "OpenAI hit max tool iterations before finalizing the analysis.", sorted(set(found_tickers))
    except Exception as exc:
        return f"OpenAI error: {exc}", []


def run_gemini_logic(messages, model_name=GEMINI_MODEL):
    """Execute Gemini function calling with a multi-turn tool loop."""
    try:
        client = get_gemini_client()
        contents = []
        system_instruction = SYSTEM_PROMPT
        found_tickers: list[str] = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant" and content:
                contents.append({"role": "model", "parts": [{"text": content}]})

        for _ in range(MAX_TOOL_ITERATIONS):
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config={
                    "system_instruction": system_instruction,
                    "tools": TOOLS_GEMINI,
                    "temperature": 0.4,
                },
            )

            tool_calls = []
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call") and part.function_call is not None:
                        tool_calls.append(part.function_call)

            if not tool_calls:
                return response.text or "", sorted(set(found_tickers))

            for func_call in tool_calls:
                func_name = func_call.name
                func_args = dict(func_call.args)
                result = _dispatch_tool(func_name, func_args, found_tickers)
                contents.append({
                    "role": "model",
                    "parts": [{"function_call": {"name": func_name, "args": func_args}}],
                })
                contents.append({
                    "role": "user",
                    "parts": [{"function_response": {"name": func_name, "response": {"result": result}}}],
                })

        return "Gemini hit max tool iterations before finalizing the analysis.", sorted(set(found_tickers))
    except Exception as exc:
        return f"Gemini error: {exc}", []


def run_claude_logic(messages, model_name=CLAUDE_MODEL):
    """Execute Claude tool-use logic with the same tool surface."""
    try:
        client = get_claude_client()
        claude_messages = []
        found_tickers: list[str] = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                claude_messages.append({"role": "user", "content": content})
            elif role == "assistant" and content:
                claude_messages.append({"role": "assistant", "content": content})

        cached_system = [{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }]
        cached_tools = [dict(tool) for tool in TOOLS_CLAUDE]
        cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

        for _ in range(MAX_TOOL_ITERATIONS):
            response = client.messages.create(
                model=model_name,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=cached_system,
                tools=cached_tools,
                messages=claude_messages,
            )

            if response.stop_reason != "tool_use":
                final_text = "".join(block.text for block in response.content if hasattr(block, "text"))
                return final_text, sorted(set(found_tickers))

            claude_messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = _dispatch_tool(block.name, block.input, found_tickers)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            claude_messages.append({"role": "user", "content": tool_results})

        return "Claude hit max tool iterations before finalizing the analysis.", sorted(set(found_tickers))
    except Exception as exc:
        return f"Claude error: {exc}", []


def run_smart_agent(messages, model_choice=CLAUDE_MODEL):
    """Execute the selected AI analyst."""
    try:
        if "gemini" in model_choice.lower():
            return run_gemini_logic(messages, model_choice)
        if "claude" in model_choice.lower():
            return run_claude_logic(messages, model_choice)
        return run_openai_logic(messages, model_choice)
    except Exception as exc:
        return f"Agent execution error: {exc}", []
