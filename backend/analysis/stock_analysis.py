"""Shared stock analysis pipeline — used by single-stock and portfolio views."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd

from analysis.research import (
    analyze_company_research,
    merge_yahoo_fundamentals,
    yahoo_snapshot_fields,
)
from analysis.sector_rotation import analyze_sector_rotation
from analysis.technical import compute_all_indicators
from analysis.llm_verdict import build_llm_verdict
from data.disclosures import fetch_recent_disclosures
from data.fetcher import (
    get_balance_sheet,
    get_earnings_dates,
    get_fundamentals,
    get_income_statement,
    get_news,
    get_stock_data,
    resolve_indian_symbol,
    yfinance_enabled,
)
from data.indian_api import (
    fetch_company_research,
    fundamentals_from_snapshot,
    history_to_ohlcv,
    is_configured as indian_api_configured,
)


def fetch_analysis_inputs(symbol: str, fast_filings: bool = True) -> dict[str, Any]:
    """Fetch research inputs. Yahoo fundamentals always run as backup when enabled."""
    fetchers: dict[str, Any] = {
        "news": lambda: get_news(symbol),
        "indian_api": lambda: fetch_company_research(symbol),
        "disclosures": lambda: fetch_recent_disclosures(
            symbol,
            extract_evidence=not fast_filings,
        ),
    }
    if yfinance_enabled():
        fetchers.update(
            {
                "fundamentals": lambda: get_fundamentals(symbol),
                "balance_sheet": lambda: get_balance_sheet(symbol),
                "income_statement": lambda: get_income_statement(symbol),
                "earnings": lambda: get_earnings_dates(symbol),
            }
        )
    with ThreadPoolExecutor(max_workers=len(fetchers)) as executor:
        futures = {name: executor.submit(fetcher) for name, fetcher in fetchers.items()}
        results = {name: future.result() for name, future in futures.items()}

    results.setdefault("fundamentals", {"company_name": symbol})
    results.setdefault("balance_sheet", {"available": False})
    results.setdefault("income_statement", {"available": False})
    results.setdefault("earnings", [])
    return results


def assemble_research(symbol: str, inputs: dict[str, Any], exchange: str = "NSE") -> dict[str, Any]:
    """Build snapshot + research, filling IndianAPI gaps from Yahoo Finance."""
    indian_api = inputs["indian_api"]
    snapshot = dict(indian_api.get("snapshot") or {})
    yahoo_fundamentals = inputs.get("fundamentals") or {}
    used_yahoo = False

    if not _snapshot_has_profile(snapshot) and yahoo_fundamentals:
        snapshot.update(yahoo_snapshot_fields(yahoo_fundamentals))
        used_yahoo = True

    if indian_api_configured() and _snapshot_has_metrics(snapshot):
        fundamentals = _fill_missing_fundamentals(
            fundamentals_from_snapshot(snapshot, symbol),
            yahoo_fundamentals,
        )
        if fundamentals.get("source") == "yahoo_finance":
            used_yahoo = True
    else:
        fundamentals = yahoo_fundamentals or {"company_name": symbol}
        if yahoo_fundamentals.get("pe_ratio") is not None or yahoo_fundamentals.get("industry"):
            used_yahoo = True

    sector_rotation = analyze_sector_rotation(snapshot.get("industry"))
    research = analyze_company_research(
        snapshot,
        indian_api.get("historical_stats") or {},
        indian_api.get("market_history") or {},
        inputs.get("disclosures") or {},
        sector_rotation,
    )
    merged = merge_yahoo_fundamentals(
        research,
        fundamentals,
        inputs.get("balance_sheet") or {},
        inputs.get("income_statement") or {},
    )
    if merged.get("fundamental_source") == "yahoo_finance":
        used_yahoo = True
    return {
        "snapshot": snapshot,
        "fundamentals": fundamentals,
        "research": merged,
        "sector_rotation": sector_rotation,
        "used_yahoo_fundamentals": used_yahoo,
    }


def _snapshot_has_profile(snapshot: dict[str, Any]) -> bool:
    return bool(snapshot.get("companyName") or snapshot.get("industry"))


def _snapshot_has_metrics(snapshot: dict[str, Any]) -> bool:
    return bool(snapshot.get("keyMetrics") or snapshot.get("companyName"))


def _fill_missing_fundamentals(primary: dict[str, Any], backup: dict[str, Any]) -> dict[str, Any]:
    if not backup:
        return primary
    filled = dict(primary)
    used_backup = False
    for key, value in backup.items():
        if filled.get(key) in (None, "", "N/A") and value not in (None, "", "N/A"):
            filled[key] = value
            used_backup = True
    if used_backup:
        filled["source"] = "yahoo_finance"
    return filled


def load_ohlcv_for_analysis(
    symbol: str,
    indian_api: dict[str, Any],
    interval: str = "1d",
) -> pd.DataFrame:
    """Prefer research market_history (already fetched) over a second 5yr pull."""
    df = history_to_ohlcv(indian_api.get("market_history") or {}, interval=interval)
    if df is not None and not df.empty:
        return df.dropna(subset=["Open", "High", "Low", "Close"])
    df = get_stock_data(symbol, period="5y", interval=interval, prefer_yahoo=False)
    return df.dropna(subset=["Open", "High", "Low", "Close"])


def run_verdict_analysis(
    symbol: str,
    exchange: str = "NSE",
    interval: str = "1d",
) -> dict[str, Any]:
    """Run the investment verdict framework for one symbol (no chart payload)."""
    resolved = resolve_indian_symbol(symbol, exchange)
    # Sequential on purpose: research includes 5yr history; reuse it for OHLCV
    # instead of racing a duplicate /historical_data call.
    inputs = fetch_analysis_inputs(resolved, True)
    indian_api = inputs["indian_api"]
    df = load_ohlcv_for_analysis(resolved, indian_api, interval)
    news = inputs["news"]
    assembled = assemble_research(resolved, inputs, exchange)
    snapshot = assembled["snapshot"]
    research = assembled["research"]
    fundamentals = assembled["fundamentals"]
    technical = compute_all_indicators(df)
    current_price = _current_price(snapshot, exchange, indian_api, df)

    company_name = snapshot.get("companyName") or fundamentals.get("company_name") or resolved
    verdict = build_llm_verdict(
        symbol=resolved,
        company_name=company_name,
        current_price=current_price,
        df=df,
        research=research,
        news=news,
        technical=technical,
        fundamentals=fundamentals,
        snapshot=snapshot,
        historical_stats=indian_api.get("historical_stats") or {},
    )

    return {
        "symbol": resolved.upper(),
        "company_name": company_name,
        "exchange": exchange.upper(),
        "current_price": round(current_price, 2),
        "verdict": verdict,
    }


def _current_price(snapshot: dict, exchange: str, indian_api: dict, df: pd.DataFrame) -> float:
    market_history = indian_api.get("market_history") or {}
    for dataset in market_history.get("datasets") or []:
        if dataset.get("metric") != "Price" or not dataset.get("values"):
            continue
        try:
            return float(dataset["values"][-1][1])
        except (IndexError, TypeError, ValueError):
            break
    prices = snapshot.get("currentPrice") or {}
    for key in (exchange.upper(), "NSE", "BSE"):
        if prices.get(key) is not None:
            try:
                return float(prices[key])
            except (TypeError, ValueError):
                continue
    return float(df["Close"].iloc[-1])
