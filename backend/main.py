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
import pandas as pd

from data.fetcher import (
    get_stock_data, get_fundamentals, get_balance_sheet,
    get_income_statement, get_earnings_dates, get_news,
    resolve_indian_symbol, search_nse_symbols,
)
from analysis.technical import compute_all_indicators
from analysis.fundamental import analyze_fundamentals
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
async def search_stocks(
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
async def chart_data(
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
async def analyze_stock(
    symbol: str,
    exchange: str = Query("NSE"),
    interval: str = Query("1d", description="Candle interval: 1d, 1wk, 1mo"),
):
    """Full analysis: OHLCV chart data + indicators + signals + fundamentals."""
    if interval not in ("1d", "1wk", "1mo"):
        raise HTTPException(status_code=400, detail="interval must be 1d, 1wk, or 1mo")
    try:
        symbol = resolve_indian_symbol(symbol, exchange)
        df = get_stock_data(symbol, period="max", interval=interval)
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        fundamentals = get_fundamentals(symbol)
        balance_sheet = get_balance_sheet(symbol)
        income_stmt = get_income_statement(symbol)
        earnings = get_earnings_dates(symbol)
        news = get_news(symbol)

        technical = compute_all_indicators(df)
        fund_analysis = analyze_fundamentals(fundamentals, balance_sheet, income_stmt)
        signals = generate_signals(df, technical, fund_analysis, earnings, news)

        # Build OHLCV for the chart
        candles = []
        volumes = []
        for idx, row in df.iterrows():
            ts = int(idx.timestamp()) if hasattr(idx, "timestamp") else int(pd.Timestamp(idx).timestamp())
            o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            candles.append({"time": ts, "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
            color = "rgba(22,163,74,0.4)" if c >= o else "rgba(220,38,38,0.4)"
            volumes.append({"time": ts, "value": int(row["Volume"]), "color": color})

        # Build chart markers from historical signals (with timestamps)
        chart_markers = _build_chart_markers(df, signals.get("historical_signals", []))

        # Build SMA overlay lines for the chart
        sma_lines = _build_sma_lines(df)

        return _sanitize({
            "symbol": symbol.upper(),
            "company_name": fundamentals.get("company_name", symbol),
            "current_price": round(float(df["Close"].iloc[-1]), 2),
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
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/api/fundamental/{symbol}")
async def fundamental_only(symbol: str, exchange: str = Query("NSE")):
    try:
        symbol = resolve_indian_symbol(symbol, exchange)
        fundamentals = get_fundamentals(symbol)
        balance_sheet = get_balance_sheet(symbol)
        income_stmt = get_income_statement(symbol)
        fund_analysis = analyze_fundamentals(fundamentals, balance_sheet, income_stmt)
        return {
            "symbol": symbol.upper(),
            "company_name": fundamentals.get("company_name", symbol),
            "fundamental": fund_analysis,
            "fundamentals_raw": fundamentals,
            "balance_sheet": balance_sheet,
            "income_statement": income_stmt,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/{symbol}")
async def news_only(symbol: str, exchange: str = Query("NSE")):
    try:
        symbol = resolve_indian_symbol(symbol, exchange)
        news = get_news(symbol)
        return {"symbol": symbol.upper(), "news": news}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sanitize(obj):
    """Replace NaN/Inf with None so JSON serialization doesn't fail."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


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
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8899)
