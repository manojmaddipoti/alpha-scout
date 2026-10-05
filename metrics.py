"""Financial metrics used by the Alpha Scout agent.

The goal is not perfect institutional data coverage. It is to provide a
consistent, non-hallucinated fact layer so the model can reason from real
numbers and state uncertainty when data is missing.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from market_sessions import completed_history
from typing import Any

import pandas as pd
import yfinance as yf


def _safe_float(value: Any):
    try:
        if value is None or pd.isna(value):
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _safe_pct(value: Any):
    value = _safe_float(value)
    return None if value is None else value * 100


def _latest_statement_value(statement: pd.DataFrame, names: list[str]):
    if statement is None or statement.empty:
        return None
    for name in names:
        if name in statement.index:
            return _safe_float(statement.loc[name].iloc[0])
    return None


def _previous_statement_value(statement: pd.DataFrame, names: list[str]):
    if statement is None or statement.empty:
        return None
    for name in names:
        if name in statement.index:
            series = statement.loc[name]
            if len(series) > 1:
                return _safe_float(series.iloc[1])
    return None


def _sum_latest(statement: pd.DataFrame, names: list[str]):
    values = [_latest_statement_value(statement, [name]) for name in names]
    values = [value for value in values if value is not None]
    return sum(values) if values else None


def _ratio(numerator, denominator):
    numerator = _safe_float(numerator)
    denominator = _safe_float(denominator)
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _cagr(first, last, periods):
    first = _safe_float(first)
    last = _safe_float(last)
    if first in (None, 0) or last is None or periods <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / periods) - 1


def _history_metrics(ticker_obj):
    try:
        hist = ticker_obj.history(period="2y", auto_adjust=False)
        hist, expected = completed_history(hist)
        if hist.empty or "Close" not in hist:
            return {"trend_status": "unavailable"}

        close = hist["Adj Close"].dropna() if "Adj Close" in hist else hist["Close"].iloc[:0]
        if close.empty:
            return {"trend_status": "unavailable: adjusted close missing"}
        latest = _safe_float(close.iloc[-1])
        ma50 = _safe_float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        ma200 = _safe_float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = _safe_float(100 - (100 / (1 + rs.iloc[-1]))) if len(close) >= 15 else None

        return {
            "latest_price": _safe_float(hist.loc[close.index[-1], "Close"]),
            "adjusted_close": latest,
            "price_as_of": close.index[-1].date().isoformat(),
            "expected_session": expected.isoformat(),
            "trend_status": "current" if close.index[-1].date() == expected else "stale",
            "trend_rule": "research signal only; no automated sell",

            "moving_average_50d": ma50,
            "moving_average_200d": ma200,
            "price_vs_50d_ma_pct": _safe_pct(_ratio(latest - ma50, ma50)) if latest and ma50 else None,
            "price_vs_200d_ma_pct": _safe_pct(_ratio(latest - ma200, ma200)) if latest and ma200 else None,
            "rsi_14d": rsi,
            "one_year_price_return_pct": _safe_pct(_ratio(close.iloc[-1] - close.iloc[-253], close.iloc[-253])) if len(close) >= 253 else None,
        }
    except Exception:
        return {"trend_status": "unavailable"}


def get_equity_metrics(ticker: str):
    ticker = ticker.upper().strip()
    stock = yf.Ticker(ticker)

    try:
        info = stock.info or {}
    except Exception:
        info = {}

    try:
        financials = stock.financials
    except Exception:
        financials = pd.DataFrame()
    try:
        cashflow = stock.cashflow
    except Exception:
        cashflow = pd.DataFrame()
    try:
        balance_sheet = stock.balance_sheet
    except Exception:
        balance_sheet = pd.DataFrame()

    revenue = _latest_statement_value(financials, ["Total Revenue", "Operating Revenue"])
    prior_revenue = _previous_statement_value(financials, ["Total Revenue", "Operating Revenue"])
    older_revenue = None
    if financials is not None and not financials.empty:
        for name in ["Total Revenue", "Operating Revenue"]:
            if name in financials.index:
                series = financials.loc[name].dropna()
                if len(series) >= 4:
                    older_revenue = _safe_float(series.iloc[3])
                break

    operating_income = _latest_statement_value(financials, ["Operating Income"])
    tax_provision = _latest_statement_value(financials, ["Tax Provision"])
    pretax_income = _latest_statement_value(financials, ["Pretax Income", "Income Before Tax"])
    tax_rate = _ratio(tax_provision, pretax_income)
    if tax_rate is None or tax_rate < 0 or tax_rate > 0.4:
        tax_rate = 0.21
    nopat = operating_income * (1 - tax_rate) if operating_income is not None else None

    total_debt = _latest_statement_value(balance_sheet, ["Total Debt"])
    if total_debt is None:
        long_debt = _latest_statement_value(balance_sheet, ["Long Term Debt"])
        short_debt = _latest_statement_value(balance_sheet, ["Current Debt", "Short Long Term Debt"])
        if long_debt is not None and short_debt is not None:
            total_debt = long_debt + short_debt
    stockholders_equity = _latest_statement_value(
        balance_sheet,
        ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"],
    )
    cash = _latest_statement_value(balance_sheet, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])
    invested_capital = None
    if all(v is not None for v in (stockholders_equity, total_debt, cash)):
        invested_capital = (stockholders_equity or 0) + (total_debt or 0) - (cash or 0)
        if invested_capital <= 0:
            invested_capital = None

    ocf = _latest_statement_value(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    capex = _latest_statement_value(cashflow, ["Capital Expenditure", "Capital Expenditures"])
    capex_abs = abs(capex) if capex is not None else None
    fcf = (ocf - capex_abs) if ocf is not None and capex_abs is not None else None
    sbc = _latest_statement_value(cashflow, ["Stock Based Compensation"])
    shares = _safe_float(info.get("sharesOutstanding"))
    market_cap = _safe_float(info.get("marketCap"))
    enterprise_value = _safe_float(info.get("enterpriseValue"))

    revenue_growth = _ratio(revenue - prior_revenue, prior_revenue) if revenue and prior_revenue else info.get("revenueGrowth")
    fcf_margin = _ratio(fcf, revenue)
    fcf_yield = _ratio(fcf, market_cap)
    fcf_per_share = _ratio(fcf, shares)
    income_period = financials.columns[0] if not financials.empty else None
    cashflow_period = cashflow.columns[0] if not cashflow.empty else None
    balance_period = balance_sheet.columns[0] if not balance_sheet.empty else None
    if income_period != cashflow_period:
        fcf_margin = None
    roic = _ratio(nopat, invested_capital) if income_period == balance_period else None
    sbc_to_ocf = _ratio(sbc, ocf) if ocf is not None and ocf > 0 else None

    gross_margin = info.get("grossMargins")
    operating_margin = info.get("operatingMargins") or _ratio(operating_income, revenue)
    rule_of_40 = None
    if revenue_growth is not None and fcf_margin is not None:
        rule_of_40 = revenue_growth + fcf_margin

    sales_marketing = _latest_statement_value(financials, ["Selling General And Administration"])
    net_new_revenue = revenue - prior_revenue if revenue is not None and prior_revenue is not None else None
    magic_number = _ratio(net_new_revenue, sales_marketing)

    metrics = {
        "ticker": ticker,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance; estimates require primary-filing verification",
        "financial_period": str(financials.columns[0]) if not financials.empty else None,
        "cashflow_period": str(cashflow.columns[0]) if not cashflow.empty else None,
        "balance_sheet_period": str(balance_sheet.columns[0]) if not balance_sheet.empty else None,
        "roic_method": "NOPAT / ending invested capital estimate; not average-capital ROIC",
        "tax_rate_assumed": tax_provision is None or pretax_income in (None, 0) or _ratio(tax_provision, pretax_income) != tax_rate,

        "company_name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "latest_price": None,  # Populated only from completed-session raw closes.
        "intraday_price": _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
        "revenue": revenue,
        "revenue_growth_yoy_pct": _safe_pct(revenue_growth),
        "revenue_cagr_3y_pct": _safe_pct(_cagr(older_revenue, revenue, 3)),
        "gross_margin_pct": _safe_pct(gross_margin),
        "operating_margin_pct": _safe_pct(operating_margin),
        "operating_cash_flow": ocf,
        "capital_expenditure": capex,
        "free_cash_flow": fcf,
        "free_cash_flow_margin_pct": _safe_pct(fcf_margin),
        "free_cash_flow_yield_pct": _safe_pct(fcf_yield),
        "free_cash_flow_per_share": fcf_per_share,
        "stock_based_compensation": sbc,
        "sbc_to_ocf_pct": _safe_pct(sbc_to_ocf),
        "nopat": nopat,
        "invested_capital": invested_capital,
        "roic_pct": _safe_pct(roic),
        "return_on_equity_pct": _safe_pct(info.get("returnOnEquity")),
        "debt_to_equity": info.get("debtToEquity"),
        "net_cash_or_debt": cash - total_debt if cash is not None and total_debt is not None else None,
        "shares_outstanding": shares,
        "forward_pe": info.get("forwardPE"),
        "trailing_pe": info.get("trailingPE"),
        "price_to_sales": info.get("priceToSalesTrailing12Months"),
        "ev_to_revenue": _ratio(enterprise_value, revenue),
        "ev_to_fcf": _ratio(enterprise_value, fcf),
        "peg_ratio": info.get("pegRatio"),
        "short_percent_of_float_pct": _safe_pct(info.get("shortPercentOfFloat")),
        "analyst_target_mean_price": info.get("targetMeanPrice"),
        "analyst_recommendation": info.get("recommendationKey"),
        "rule_of_40_pct": _safe_pct(rule_of_40),
        "magic_number": magic_number,
    }

    metrics.update(_history_metrics(stock))
    return metrics


def get_equity_metrics_json(ticker: str):
    return json.dumps(get_equity_metrics(ticker), default=str)


def get_competitor_metrics_json(target_ticker: str, competitors: list[str] | None = None):
    target_ticker = target_ticker.upper().strip()
    competitors = competitors or []
    clean_competitors = []
    for ticker in competitors:
        ticker = ticker.upper().strip()
        if ticker and ticker != target_ticker and ticker not in clean_competitors:
            clean_competitors.append(ticker)

    tickers = [target_ticker, *clean_competitors[:5]]
    rows = []
    for ticker in tickers:
        try:
            data = get_equity_metrics(ticker)
            rows.append({
                "ticker": data["ticker"],
                "company_name": data["company_name"],
                "sector": data["sector"],
                "industry": data["industry"],
                "market_cap": data["market_cap"],
                "revenue_growth_yoy_pct": data["revenue_growth_yoy_pct"],
                "gross_margin_pct": data["gross_margin_pct"],
                "free_cash_flow_margin_pct": data["free_cash_flow_margin_pct"],
                "free_cash_flow_yield_pct": data["free_cash_flow_yield_pct"],
                "roic_pct": data["roic_pct"],
                "sbc_to_ocf_pct": data["sbc_to_ocf_pct"],
                "ev_to_revenue": data["ev_to_revenue"],
                "ev_to_fcf": data["ev_to_fcf"],
                "one_year_price_return_pct": data.get("one_year_price_return_pct"),
            })
        except Exception as exc:
            rows.append({"ticker": ticker, "error": str(exc)})

    payload = {
        "target": target_ticker,
        "competitors_provided": clean_competitors,
        "note": "If peers are missing or irrelevant, use web_search to identify better public peers and call get_competitor_metrics again.",
        "rows": rows,
    }
    return json.dumps(payload, default=str)
