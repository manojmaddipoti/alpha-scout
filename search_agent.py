import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from research_evidence import ACTIVE_EVIDENCE, public_url
from valuation import calculate_valuation

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
MAX_TOOL_ITERATIONS = 12
MAX_OUTPUT_TOKENS = 12000
WEB_SEARCH_MAX_RESULTS = 5
WEB_SEARCH_CONTENT_TRUNC = 1800
SEC_SECTION_TRUNC = 10000


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found")
    return OpenAI(api_key=api_key, timeout=180.0, max_retries=1)


def get_tavily_client():
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not found")
    return TavilyClient(api_key=api_key)


def get_gemini_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found")
    return genai.Client(api_key=api_key, http_options={"timeout": 180000})


def get_claude_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found")
    return anthropic.Anthropic(api_key=api_key, timeout=180.0, max_retries=1)


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
                source_url = getattr(filing, "document_url", None)
                if not source_url:
                    primary = getattr(filing, "primary_document", None)
                    accession = str(getattr(filing, "accession_no", "")).replace("-", "")
                    cik = getattr(filing, "cik", None)
                    if primary and accession.isdigit() and str(cik).isdigit():
                        source_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{quote(str(primary), safe='')}"
                    else:
                        source_url = getattr(filing, "homepage_url", None)
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
                    try:
                        full_text = filing.text()
                        if full_text:
                            excerpts["document_excerpt"] = str(full_text)[:SEC_SECTION_TRUNC * 2]
                    except Exception:
                        pass
                if not excerpts and source_url and public_url(source_url):
                    try:
                        extracted = get_tavily_client().extract(
                            urls=[source_url], extract_depth="advanced", format="text",
                            query="management discussion risk factors revenue margins cash flow liquidity financial results guidance",
                            chunks_per_source=8,
                        )
                        pages = extracted.get("results", [])
                        if pages and pages[0].get("raw_content"):
                            excerpts["targeted_document_excerpt"] = pages[0]["raw_content"][:SEC_SECTION_TRUNC * 2]
                    except Exception:
                        pass
                if not excerpts:
                    gaps.append(label + " filing metadata available but document text unavailable")
                documents.append({"form": filing.form, "filing_date": str(filing.filing_date),
                                  "url": source_url, "content_status": "extracted" if excerpts else "metadata_only",
                                  "excerpts": excerpts})
            except Exception:
                gaps.append(label + " retrieval failed")
        return json.dumps({"ticker": ticker, "documents": documents, "gaps": gaps,
                           "limitations": "Excerpts may omit material sections or earnings attachments. Latest 6-K may not be earnings; verify with issuer release."}, default=str)
    except Exception:
        return json.dumps({"error": "SEC filing retrieval failed", "ticker": ticker})


def get_financial_metrics(ticker: str):
    """Fetch corrected financial metrics with estimated ending-capital ROIC and FCF fields."""
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
        return json.dumps({"error": "Web search failed", "type": type(exc).__name__})


def read_source(url):
    """Hosted extraction only for public URLs actually returned during this run."""
    log = ACTIVE_EVIDENCE.get()
    if log is None or not public_url(url) or url not in log.urls:
        return json.dumps({"error": "URL must be a public source returned by this research run"})
    try:
        result = get_tavily_client().extract(urls=[url], extract_depth="advanced", format="text")
        pages = [{"url": item.get("url"), "excerpt": (item.get("raw_content") or "")[:22000]}
                 for item in result.get("results", [])]
        return json.dumps({"documents": pages, "gaps": result.get("failed_results", []),
                           "limitation": "Bounded extracted text; not necessarily the full document"})
    except Exception:
        return json.dumps({"error": "Source extraction failed", "url": url})


def _dispatch_tool(name: str, args: dict, found_tickers: list[str]) -> str:
    try:
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object")
        output = _dispatch_valid_tool(name, args, found_tickers)
        log = ACTIVE_EVIDENCE.get()
        return log.record(name, args, output) if log is not None else output
    except Exception as exc:
        output = json.dumps({"error": "Tool failed", "tool": name, "type": type(exc).__name__})
        log = ACTIVE_EVIDENCE.get()
        return log.record(name, args if isinstance(args, dict) else {}, output) if log is not None else output


def _dispatch_valid_tool(name: str, args: dict, found_tickers: list[str]) -> str:
    if name == "calculate_valuation":
        return json.dumps(calculate_valuation(args), allow_nan=False)
    if name == "read_source":
        return read_source(args["url"])
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
        "description": "Fetch forensic financial metrics for one ticker: estimated ending-capital ROIC, ROE, OCF, FCF, FCF yield, SBC/OCF, valuation, consensus, short interest, technicals, sector, and industry.",
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


TOOL_SPECS.extend([
    {"name": "read_source", "description": "Read substantive text from a primary or other public source URL already returned by tools in this run. Search snippets alone are insufficient evidence.",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "calculate_valuation", "description": "Calculate bear/base/bull future target prices and returns. equity_per_share: terminal metric is earnings/FCF/FFO/book value per share; enterprise_multiple: metric and net debt use identical currency units and shares use consistent units. No DCF or forecast verification. Include assumptions and explicit dividends in every case.",
     "parameters": {"type": "object", "properties": {
         "method": {"type": "string", "enum": ["equity_per_share", "enterprise_multiple"]},
         "currency": {"type": "string"}, "current_price": {"type": "number"}, "years": {"type": "number"},
         "scenarios": {"type": "array", "items": {"type": "object", "properties": {
             "name": {"type": "string", "enum": ["bear", "base", "bull"]},
             "terminal_metric": {"type": "number"}, "exit_multiple": {"type": "number"},
             "terminal_net_debt": {"type": "number"}, "terminal_shares": {"type": "number"},
             "cumulative_dividends_per_share": {"type": "number"}},
             "required": ["name", "terminal_metric", "exit_multiple", "cumulative_dividends_per_share"]}}},
         "required": ["method", "currency", "current_price", "years", "scenarios"]}}
])


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


def provider_error(provider, exc):
    if isinstance(exc, ResearchFailure):
        return exc
    message = str(exc).lower()
    if any(term in message for term in ("insufficient_quota", "credit_balance", "no credits", "credit balance", "billing")):
        return ResearchFailure(f"{provider} API credits or quota are exhausted. Fund that provider or select another configured model.")
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 404:
        return ResearchFailure(f"{provider} configured model is unavailable for this API; check its model ID and account access.")
    if status == 429:
        return ResearchFailure(f"{provider} rate limit reached; retry later.")
    if status in (401, 403):
        return ResearchFailure(f"{provider} authentication or model access failed; check deployment credentials and access.")
    return ResearchFailure(f"{provider} request failed ({type(exc).__name__}); research did not complete.")


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
        raise provider_error("OpenAI", exc) from exc


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
        raise provider_error("Gemini", exc) from exc


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
        raise provider_error("Claude", exc) from exc


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
