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
from model_config import CLAUDE_MODEL, GEMINI_MODEL, OPENAI_MODEL, provider_for_model

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

        sec_identity = os.getenv("SEC_IDENTITY")
        if not sec_identity:
            return json.dumps({"error": "SEC_IDENTITY must be configured for filing retrieval"})
        set_identity(sec_identity)
        company = Company(ticker)
        documents = []
        gaps = []
        for label, forms in [("annual", ["10-K", "20-F"]), ("interim", ["10-Q", "6-K"]), ("current", ["8-K"] )]:
            try:
                filings = company.get_filings(form=forms)
                filing = filings.latest() if filings else None
                if not filing:
                    gaps.append(label + " filing unavailable")
                    continue
                excerpts = {}
                try:
                    obj = filing.obj()
                    for key, attrs in {"management_discussion": ("management_discussion", "mda", "item_7"),
                                       "risk_factors": ("risk_factors", "item_1a")}.items():
                        for attr in attrs:
                            value = getattr(obj, attr, None)
                            if value:
                                excerpts[key] = str(value)[:SEC_SECTION_TRUNC]
                                break
                except Exception:
                    pass
                if not excerpts:
                    excerpts["document_excerpt"] = str(filing.text())[:SEC_SECTION_TRUNC * 2]
                documents.append({"form": filing.form, "filing_date": str(filing.filing_date),
                                  "url": getattr(filing, "document_url", None) or getattr(filing, "homepage_url", None),
                                  "excerpts": excerpts})
            except Exception:
                gaps.append(label + " retrieval failed")
        return json.dumps({"ticker": ticker, "documents": documents, "gaps": gaps,
                           "limitations": "Excerpts may omit material sections or earnings attachments. Latest 6-K may not be earnings; verify with issuer release."}, default=str)
    except Exception:
        return json.dumps({"error": "SEC filing retrieval failed", "ticker": ticker})


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
    try:
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object")
        return _dispatch_valid_tool(name, args, found_tickers)
    except Exception as exc:
        return json.dumps({"error": "Tool failed", "tool": name, "type": type(exc).__name__})


def _dispatch_valid_tool(name: str, args: dict, found_tickers: list[str]) -> str:
    if name == "web_search":
        return web_search(args["query"])
    if name == "get_financial_metrics":
        ticker = args["ticker"].strip().upper()
        found_tickers.append(ticker)
        return get_financial_metrics(ticker)
    if name == "get_competitor_metrics":
        target = args["target_ticker"].strip().upper()
        competitors = [
            ticker.strip().upper()
            for ticker in args.get("competitors", [])
            if ticker.strip()
        ]
        found_tickers.extend([target, *competitors])
        return get_competitor_metrics(target, competitors)
    if name == "get_sec_filing":
        ticker = args["ticker"].strip().upper()
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


class ResearchFailure(RuntimeError):
    """No complete research result is available; never save this as a verdict."""


def run_openai_logic(messages, model_name=OPENAI_MODEL):
    try:
        client = get_openai_client()
        conversation = [dict(m) for m in messages]
        found_tickers = []
        for _ in range(MAX_TOOL_ITERATIONS):
            response = client.responses.create(
                model=model_name, input=conversation,
                tools=[{"type": "function", **spec, "strict": False} for spec in TOOL_SPECS],
                max_output_tokens=16000, store=False,
                include=["reasoning.encrypted_content"],
            )
            if response.status != "completed":
                raise ResearchFailure("OpenAI returned an incomplete response")
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                if not response.output_text.strip():
                    raise ResearchFailure("OpenAI returned no research text")
                return response.output_text, sorted(set(found_tickers))
            conversation.extend(item.model_dump(exclude_none=True) for item in response.output)
            for call in calls:
                result = _dispatch_tool(call.name, json.loads(call.arguments or "{}"), found_tickers)
                conversation.append({"type": "function_call_output", "call_id": call.call_id, "output": result})
        raise ResearchFailure("OpenAI exceeded the research tool budget")
    except ResearchFailure:
        raise
    except Exception as exc:
        raise ResearchFailure("OpenAI request failed. Check model access, API credits and provider status.") from exc


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
                if not response.candidates or str(response.candidates[0].finish_reason).split(".")[-1] != "STOP" or not (response.text or "").strip():
                    raise ResearchFailure("Gemini returned incomplete or empty research")
                return response.text, sorted(set(found_tickers))

            # Preserve original content, including provider thought signatures.
            contents.append(response.candidates[0].content)
            results = []
            for func_call in tool_calls:
                result = _dispatch_tool(func_call.name, dict(func_call.args), found_tickers)
                results.append({"function_response": {"name": func_call.name, "response": {"result": result}}})
            contents.append({"role": "user", "parts": results})

        raise ResearchFailure("Gemini exceeded the research tool budget")
    except Exception as exc:
        raise ResearchFailure("Gemini research failed. Check model access, API credits and provider status.") from exc


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
            "text": "\n\n".join(m["content"] for m in messages if m["role"] == "system") or SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }]
        cached_tools = [dict(tool) for tool in TOOLS_CLAUDE]
        cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

        for _ in range(MAX_TOOL_ITERATIONS):
            with client.messages.stream(
                model=model_name, max_tokens=32000,
                thinking={"type": "adaptive"},
                system=cached_system, tools=cached_tools, messages=claude_messages,
            ) as stream:
                response = stream.get_final_message()

            if response.stop_reason != "tool_use":
                if response.stop_reason != "end_turn":
                    raise ResearchFailure("Claude returned incomplete research")
                final_text = "".join(block.text for block in response.content if hasattr(block, "text"))
                if not final_text.strip():
                    raise ResearchFailure("Claude returned no research text")
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

        raise ResearchFailure("Claude exceeded the research tool budget")
    except Exception as exc:
        raise ResearchFailure("Claude research failed. Check model access, API credits and provider status.") from exc


def run_smart_agent(messages, model_choice=CLAUDE_MODEL):
    """Execute the selected AI analyst."""
    try:
        provider = provider_for_model(model_choice)
        if provider == "gemini":
            return run_gemini_logic(messages, model_choice)
        if provider == "claude":
            return run_claude_logic(messages, model_choice)
        return run_openai_logic(messages, model_choice)
    except Exception as exc:
        raise ResearchFailure(str(exc) if isinstance(exc, ResearchFailure) else "Research execution failed") from exc
