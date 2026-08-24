"""
Stock Market Analyzer — FastAPI backend.
Provides OHLCV chart data, technical analysis, fundamental analysis,
and entry/exit signals with chart-plottable markers.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import traceback
import math
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

from data.fetcher import (
    get_stock_data, get_fundamentals, get_balance_sheet,
    get_income_statement, get_earnings_dates, get_news,
    resolve_indian_symbol, search_nse_symbols,
)
from data.indian_api import fetch_company_research, fetch_ipo_data
from data.disclosures import fetch_recent_disclosures
from analysis.technical import compute_all_indicators
from analysis.fundamental import analyze_fundamentals
from analysis.research import analyze_company_research
from analysis.documents import analyze_offer_document
from analysis.sector_rotation import analyze_sector_rotation
from analysis.scoring import generate_signals

app = FastAPI(
    title="Stock Market Analyzer",
    description="Technical & fundamental analysis with entry/exit signals",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/api/health")
async def health():
    return {"status": "running", "service": "Stock Market Analyzer API"}


@app.get("/api/search")
def search_stocks(
    q: str = Query("", description="Search query"),
    exchange: str = Query("NSE", description="Exchange: NSE or BSE"),
    limit: int = Query(15),
):
    """Search NSE/BSE stock symbols."""
    results = search_nse_symbols(q, limit=limit)
    suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
    return {
        "query": q,
        "exchange": exchange.upper(),
        "results": [
            {"symbol": r["symbol"], "name": r["name"], "yf_symbol": r["symbol"] + suffix}
            for r in results
        ],
    }


@app.get("/api/chart/{symbol}")
def chart_data(
    symbol: str,
    exchange: str = Query("NSE"),
):
    """OHLCV daily candlestick data formatted for Lightweight Charts."""
    try:
        symbol = resolve_indian_symbol(symbol, exchange)
        df = get_stock_data(symbol, period="max", interval="1d")
        candles = []
        volumes = []
        for idx, row in df.iterrows():
            ts = int(idx.timestamp()) if hasattr(idx, "timestamp") else int(pd.Timestamp(idx).timestamp())
            o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            candles.append({"time": ts, "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
            color = "rgba(22,163,74,0.4)" if c >= o else "rgba(220,38,38,0.4)"
            volumes.append({"time": ts, "value": int(row["Volume"]), "color": color})
        return {"symbol": symbol.upper(), "candles": candles, "volumes": volumes}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analyze/{symbol}")
def analyze_stock(
    symbol: str,
    exchange: str = Query("NSE"),
    interval: str = Query("1d", description="Candle interval: 1d, 1wk, 1mo"),
):
    """Full analysis: OHLCV chart data + indicators + signals + fundamentals."""
    if interval not in ("1d", "1wk", "1mo"):
        raise HTTPException(status_code=400, detail="interval must be 1d, 1wk, or 1mo")
    try:
        symbol = resolve_indian_symbol(symbol, exchange)

        # CRITICAL: OHLCV is the only required call — everything else degrades gracefully
        df = get_stock_data(symbol, period="max", interval=interval)
        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        # Historical chart data remains Yahoo-backed because IndianAPI's
        # history endpoint does not provide full OHLC candles.
        inputs = _fetch_analysis_inputs(symbol)
        fundamentals = inputs["fundamentals"]
        balance_sheet = inputs["balance_sheet"]
        income_stmt = inputs["income_statement"]
        earnings = inputs["earnings"]
        news = inputs["news"]
        indian_api = inputs["indian_api"]
        disclosures = inputs["disclosures"]
        snapshot = indian_api.get("snapshot") or {}
        sector_rotation = analyze_sector_rotation(snapshot.get("industry"))
        research = analyze_company_research(
            snapshot,
            indian_api.get("historical_stats") or {},
            indian_api.get("market_history") or {},
            disclosures,
            sector_rotation,
        )

        technical = compute_all_indicators(df)
        fund_analysis = analyze_fundamentals(fundamentals, balance_sheet, income_stmt)
        signals = generate_signals(df, technical, fund_analysis, earnings, news)

        candles = []
        volumes = []
        for idx, row in df.iterrows():
            ts = int(idx.timestamp()) if hasattr(idx, "timestamp") else int(pd.Timestamp(idx).timestamp())
            o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            candles.append({"time": ts, "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
            color = "rgba(22,163,74,0.4)" if c >= o else "rgba(220,38,38,0.4)"
            volumes.append({"time": ts, "value": int(row["Volume"]), "color": color})

        chart_markers = _build_chart_markers(df, signals.get("historical_signals", []))
        sma_lines = _build_sma_lines(df)

        live_price, live_price_source, live_price_as_of = _indian_api_price(
            snapshot,
            exchange,
            indian_api.get("market_history") or {},
        )
        last_bar_as_of = _index_iso(df.index[-1])
        warnings = _build_data_warnings(indian_api, last_bar_as_of)

        return _sanitize({
            "symbol": symbol.upper(),
            "company_name": snapshot.get("companyName") or fundamentals.get("company_name", symbol),
            "current_price": round(live_price or float(df["Close"].iloc[-1]), 2),
            "current_price_source": (
                live_price_source
                if live_price is not None
                else "Yahoo Finance historical close"
            ),
            "current_price_as_of": live_price_as_of or last_bar_as_of,
            "analysis_as_of": datetime.now(timezone.utc).isoformat(),
            "interval": interval,
            "chart": {"candles": candles, "volumes": volumes},
            "chart_markers": chart_markers,
            "sma_lines": sma_lines,
            "signals": signals,
            "technical": technical,
            "fundamental": fund_analysis,
            "fundamentals_raw": fundamentals,
            "balance_sheet": balance_sheet,
            "income_statement": income_stmt,
            "earnings": earnings,
            "news": news,
            "research": research,
            "data_provenance": {
                "live_snapshot": indian_api.get("provenance", {}).get("snapshot"),
                "research": indian_api.get("provenance", {}),
                "official_filings": disclosures.get("provenance"),
                "sector_rotation": sector_rotation.get("provenance"),
                "ohlcv": {
                    "provider": "Yahoo Finance",
                    "status": "ok",
                    "as_of": last_bar_as_of,
                    "usage": "completed candles for technical indicators",
                },
            },
            "data_warnings": warnings,
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        error_msg = str(e)
        if "Too Many Requests" in error_msg or "Rate" in error_msg or "429" in error_msg:
            raise HTTPException(status_code=429, detail="Yahoo Finance rate limit — please wait 30 seconds and try again.")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {error_msg}")


@app.get("/api/fundamental/{symbol}")
def fundamental_only(symbol: str, exchange: str = Query("NSE")):
    try:
        symbol = resolve_indian_symbol(symbol, exchange)
        fundamentals = get_fundamentals(symbol)
        balance_sheet = get_balance_sheet(symbol)
        income_stmt = get_income_statement(symbol)
        indian_api = fetch_company_research(symbol)
        disclosures = fetch_recent_disclosures(symbol)
        snapshot = indian_api.get("snapshot") or {}
        sector_rotation = analyze_sector_rotation(snapshot.get("industry"))
        research = analyze_company_research(
            snapshot,
            indian_api.get("historical_stats") or {},
            indian_api.get("market_history") or {},
            disclosures,
            sector_rotation,
        )
        fund_analysis = analyze_fundamentals(fundamentals, balance_sheet, income_stmt)
        return {
            "symbol": symbol.upper(),
            "company_name": fundamentals.get("company_name", symbol),
            "fundamental": fund_analysis,
            "fundamentals_raw": fundamentals,
            "balance_sheet": balance_sheet,
            "income_statement": income_stmt,
            "research": research,
            "data_provenance": {
                "indian_api": indian_api.get("provenance", {}),
                "official_filings": disclosures.get("provenance"),
                "sector_rotation": sector_rotation.get("provenance"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/{symbol}")
def news_only(symbol: str, exchange: str = Query("NSE")):
    try:
        symbol = resolve_indian_symbol(symbol, exchange)
        news = get_news(symbol)
        return {"symbol": symbol.upper(), "news": news}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ipo")
def ipo_data():
    """Latest IPO records from IndianAPI; DRHP URLs depend on provider coverage."""
    result = fetch_ipo_data()
    return _sanitize(result)


@app.get("/api/ipo/{company}/research")
def ipo_research(company: str):
    """Locate an IPO document and extract the core DRHP/RHP research sections."""
    result = fetch_ipo_data()
    ipo_payload = result.get("data") or {}
    record = _find_ipo_record(ipo_payload, company)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No IPO record found for {company}")
    document_url = record.get("document_url")
    if not document_url:
        raise HTTPException(
            status_code=404,
            detail=f"IPO record found for {company}, but no offer document URL is available",
        )
    try:
        document_analysis = analyze_offer_document(document_url)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Offer document could not be read: {exc}",
        )
    return _sanitize(
        {
            "ipo": record,
            "document_analysis": document_analysis,
            "data_provenance": result.get("provenance"),
        }
    )


def _sanitize(obj):
    """Replace NaN/Inf with None so JSON serialization doesn't fail."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _indian_api_price(
    snapshot: dict,
    exchange: str,
    market_history: dict,
) -> tuple[float | None, str | None, str | None]:
    for dataset in market_history.get("datasets") or []:
        if dataset.get("metric") != "Price" or not dataset.get("values"):
            continue
        latest = dataset["values"][-1]
        try:
            return float(latest[1]), "IndianAPI market history", str(latest[0])
        except (IndexError, TypeError, ValueError):
            break
    prices = snapshot.get("currentPrice") or {}
    value = prices.get(exchange.upper())
    try:
        if value is None:
            return None, None, None
        return float(value), "IndianAPI snapshot", None
    except (TypeError, ValueError):
        return None, None, None


def _index_iso(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _build_data_warnings(indian_api: dict, last_bar_as_of: str) -> list[str]:
    warnings = [
        "Technical indicators use the latest completed Yahoo Finance candle, not an intraday candle.",
    ]
    snapshot_status = (
        indian_api.get("provenance", {}).get("snapshot", {}).get("status")
    )
    if snapshot_status != "ok":
        warnings.append(
            "IndianAPI live snapshot is unavailable; displayed price falls back to the latest historical close."
        )
    if not indian_api.get("snapshot"):
        warnings.append("IndianAPI fundamental snapshot is unavailable.")
    warnings.append(f"Latest technical-analysis candle: {last_bar_as_of}")
    return warnings


def _find_ipo_record(payload: dict, company: str) -> dict | None:
    query = company.strip().lower()
    for records in payload.values():
        if not isinstance(records, list):
            continue
        for record in records:
            name = str(record.get("name", "")).lower()
            symbol = str(record.get("symbol", "")).lower()
            if query == symbol or query in name:
                return record
    return None


def _fetch_analysis_inputs(symbol: str) -> dict:
    fetchers = {
        "fundamentals": lambda: get_fundamentals(symbol),
        "balance_sheet": lambda: get_balance_sheet(symbol),
        "income_statement": lambda: get_income_statement(symbol),
        "earnings": lambda: get_earnings_dates(symbol),
        "news": lambda: get_news(symbol),
        "indian_api": lambda: fetch_company_research(symbol),
        "disclosures": lambda: fetch_recent_disclosures(symbol),
    }
    with ThreadPoolExecutor(max_workers=len(fetchers)) as executor:
        futures = {
            name: executor.submit(fetcher)
            for name, fetcher in fetchers.items()
        }
        return {name: future.result() for name, future in futures.items()}


def _build_chart_markers(df: pd.DataFrame, historical_signals: list) -> list:
    """Convert historical signals to Lightweight Charts marker format with timestamps."""
    date_to_ts = {}
    for idx in df.index:
        date_str = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
        date_to_ts[date_str] = int(idx.timestamp()) if hasattr(idx, "timestamp") else int(pd.Timestamp(idx).timestamp())

    markers = []
    for sig in historical_signals:
        ts = date_to_ts.get(sig["date"])
        if ts is None:
            continue
        is_entry = sig["type"] == "entry"
        conf = sig.get("confidence", 60)
        markers.append({
            "time": ts,
            "position": "belowBar" if is_entry else "aboveBar",
            "color": "#16a34a" if is_entry else "#dc2626",
            "shape": "arrowUp" if is_entry else "arrowDown",
            "text": f"{conf}%",
            "size": 2 if sig.get("strength") == "strong" else 1,
            "price": sig["price"],
            "reason": sig["reason"],
            "strength": sig.get("strength", "moderate"),
            "confidence": conf,
            "stop": sig.get("stop"),
            "tp1": sig.get("tp1"),
            "tp2": sig.get("tp2"),
            "rr": sig.get("rr"),
        })
    return markers


def _build_sma_lines(df: pd.DataFrame) -> dict:
    """Build SMA line data for chart overlay."""
    close = df["Close"]
    result = {}
    for period in [20, 50, 200]:
        if len(close) < period:
            continue
        sma = close.rolling(window=period).mean()
        line_data = []
        for idx, val in sma.items():
            if pd.isna(val):
                continue
            ts = int(idx.timestamp()) if hasattr(idx, "timestamp") else int(pd.Timestamp(idx).timestamp())
            line_data.append({"time": ts, "value": round(float(val), 2)})
        result[f"sma_{period}"] = line_data
    return result


# Serve frontend
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/{path:path}")
async def serve_frontend(path: str = ""):
    file_path = FRONTEND_DIR / path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8899))
    uvicorn.run(app, host="0.0.0.0", port=port)
