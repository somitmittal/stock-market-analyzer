"""
Stock Market Analyzer — FastAPI backend.
Provides OHLCV chart data, technical analysis, fundamental analysis,
and entry/exit signals with chart-plottable markers.
"""
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os
import traceback
import math
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, EmailStr, Field
import pandas as pd

from db import init_db
from auth import get_current_user, login_user, register_user
from portfolios import (
    list_portfolios,
    list_portfolios_with_holdings,
    create_portfolio,
    get_portfolio,
    delete_portfolio,
    add_holding,
    remove_holding,
)
from analysis.concall import summarize_concall_document

from data.fetcher import (
    get_stock_data, get_news,
    resolve_indian_symbol, search_nse_symbols,
)
from data.indian_api import (
    fetch_ipo_data,
)
from analysis.technical import compute_all_indicators
from analysis.fundamental import analyze_fundamentals
from analysis.documents import analyze_offer_document
from analysis.scoring import generate_signals
from analysis.stock_analysis import (
    assemble_research,
    fetch_analysis_inputs,
    load_ohlcv_for_analysis,
)
from analysis.llm_verdict import build_llm_verdict
from analysis.gemini_client import is_configured as gemini_configured
from trading import (
    add_watchlist,
    get_quote,
    get_wallet,
    list_orders,
    list_positions,
    list_watchlist,
    market_overview,
    place_stock_order,
    remove_watchlist,
)
from mutual_funds import (
    buy_lumpsum,
    create_sip,
    get_fund,
    list_funds,
    list_mf_holdings,
    list_sips,
    pause_sip,
    portfolio_summary,
)

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


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = ""


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class PortfolioBody(BaseModel):
    name: str


class HoldingBody(BaseModel):
    symbol: str
    exchange: str = "NSE"


class ConcallSummaryBody(BaseModel):
    attachment_url: str
    subject: str | None = None


class StockOrderBody(BaseModel):
    symbol: str
    exchange: str = "NSE"
    side: str
    quantity: float | None = None
    amount: float | None = None


class WatchlistBody(BaseModel):
    symbol: str
    exchange: str = "NSE"


class MfBuyBody(BaseModel):
    fund_id: str
    amount: float = Field(gt=0)


class MfSipBody(BaseModel):
    fund_id: str
    amount: float = Field(gt=0)
    frequency: str = "monthly"
    invest_now: bool = True


@app.on_event("startup")
def on_startup():
    init_db()


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
        df = get_stock_data(symbol, period="5y", interval="1d")
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
    response: Response,
    exchange: str = Query("NSE"),
    interval: str = Query("1d", description="Candle interval: 1d, 1wk, 1mo"),
):
    """Full analysis: OHLCV chart data + indicators + signals + fundamentals."""
    response.headers["Cache-Control"] = "no-store"
    if interval not in ("1d", "1wk", "1mo"):
        raise HTTPException(status_code=400, detail="interval must be 1d, 1wk, or 1mo")
    try:
        symbol = resolve_indian_symbol(symbol, exchange)

        # Research already fetches 5yr history — reuse it for the chart so we do
        # not fire a second /historical_data request in parallel (was doubling quota).
        inputs = fetch_analysis_inputs(symbol, True)
        indian_api = inputs["indian_api"]
        df = load_ohlcv_for_analysis(symbol, indian_api, interval)
        assembled = assemble_research(symbol, inputs, exchange)
        snapshot = assembled["snapshot"]
        fundamentals = assembled["fundamentals"]
        research = assembled["research"]
        sector_rotation = assembled["sector_rotation"]
        balance_sheet = inputs["balance_sheet"]
        income_stmt = inputs["income_statement"]
        earnings = inputs["earnings"]
        news = inputs["news"]
        disclosures = inputs["disclosures"]
        technical = compute_all_indicators(df)
        live_price, live_price_source, live_price_as_of = _indian_api_price(
            snapshot,
            exchange,
            indian_api.get("market_history") or {},
        )
        current_price = live_price or float(df["Close"].iloc[-1])
        company_name = snapshot.get("companyName") or fundamentals.get("company_name", symbol)
        investment_verdict = build_llm_verdict(
            symbol=symbol,
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

        last_bar_as_of = _index_iso(df.index[-1])
        ohlcv_provider = df.attrs.get("ohlcv_provider") or "Unknown"
        synthetic_ohlc = bool(df.attrs.get("synthetic_ohlc"))
        warnings = _build_data_warnings(
            indian_api,
            disclosures,
            last_bar_as_of,
            ohlcv_provider,
            synthetic_ohlc,
        )
        if os.getenv("GEMINI_API_KEY") and not gemini_configured():
            warnings.append(
                "GEMINI_API_KEY looks invalid (check for a duplicate paste in .env). "
                "Using rule-based verdict until fixed."
            )
        elif gemini_configured() and investment_verdict.get("analysis_source") != "gemini":
            gemini_note = investment_verdict.get("analysis_error")
            warnings.append(
                "Gemini analysis unavailable — showing rule-based verdict."
                + (f" ({gemini_note})" if gemini_note else "")
            )
        elif investment_verdict.get("analysis_source") == "gemini":
            warnings.append("Investment verdict generated by Gemini from live data.")
        if assembled.get("used_yahoo_fundamentals"):
            warnings.append(
                "IndianAPI fundamentals were incomplete, so Yahoo Finance TTM metrics "
                "were used as backup for valuation, growth, and balance-sheet sections."
            )

        return _sanitize({
            "symbol": symbol.upper(),
            "company_name": company_name,
            "current_price": round(live_price or float(df["Close"].iloc[-1]), 2),
            "current_price_source": (
                live_price_source
                if live_price is not None
                else f"{ohlcv_provider} historical close"
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
            "verdict": investment_verdict,
            "data_provenance": {
                "live_snapshot": indian_api.get("provenance", {}).get("snapshot"),
                "research": indian_api.get("provenance", {}),
                "official_filings": disclosures.get("provenance"),
                "sector_rotation": sector_rotation.get("provenance"),
                "ohlcv": {
                    "provider": ohlcv_provider,
                    "status": "ok",
                    "as_of": last_bar_as_of,
                    "synthetic_ohlc": synthetic_ohlc,
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
        inputs = fetch_analysis_inputs(symbol, fast_filings=False)
        assembled = assemble_research(symbol, inputs, exchange)
        snapshot = assembled["snapshot"]
        fundamentals = assembled["fundamentals"]
        research = assembled["research"]
        sector_rotation = assembled["sector_rotation"]
        balance_sheet = inputs["balance_sheet"]
        income_stmt = inputs["income_statement"]
        disclosures = inputs["disclosures"]
        indian_api = inputs["indian_api"]
        fund_analysis = analyze_fundamentals(fundamentals, balance_sheet, income_stmt)
        warnings = []
        if assembled.get("used_yahoo_fundamentals"):
            warnings.append(
                "IndianAPI fundamentals were incomplete; Yahoo Finance TTM metrics used as backup."
            )
        return {
            "symbol": symbol.upper(),
            "company_name": snapshot.get("companyName") or fundamentals.get("company_name", symbol),
            "fundamental": fund_analysis,
            "fundamentals_raw": fundamentals,
            "balance_sheet": balance_sheet,
            "income_statement": income_stmt,
            "research": research,
            "data_warnings": warnings,
            "data_provenance": {
                "indian_api": indian_api.get("provenance", {}),
                "official_filings": disclosures.get("provenance"),
                "sector_rotation": sector_rotation.get("provenance"),
                "fundamentals_source": (
                    "yahoo_finance" if assembled.get("used_yahoo_fundamentals") else "indian_api"
                ),
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


@app.post("/api/auth/register")
def auth_register(body: RegisterBody):
    return register_user(body.email, body.password, body.name)


@app.post("/api/auth/login")
def auth_login(body: LoginBody):
    return login_user(body.email, body.password)


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(get_current_user)):
    return {"user": user}


@app.get("/api/markets")
def markets_home():
    return market_overview()


@app.get("/api/quote/{symbol}")
def quote_symbol(symbol: str, exchange: str = Query("NSE")):
    return get_quote(symbol, exchange)


@app.get("/api/wallet")
def wallet_get(user: dict = Depends(get_current_user)):
    return get_wallet(user["id"])


@app.get("/api/watchlist")
def watchlist_get(user: dict = Depends(get_current_user)):
    return {"items": list_watchlist(user["id"])}


@app.post("/api/watchlist")
def watchlist_add(body: WatchlistBody, user: dict = Depends(get_current_user)):
    return add_watchlist(user["id"], body.symbol, body.exchange)


@app.delete("/api/watchlist/{symbol}")
def watchlist_remove(
    symbol: str,
    exchange: str = Query("NSE"),
    user: dict = Depends(get_current_user),
):
    remove_watchlist(user["id"], symbol, exchange)
    return {"ok": True}


@app.post("/api/trade/order")
def trade_order(body: StockOrderBody, user: dict = Depends(get_current_user)):
    return place_stock_order(
        user["id"],
        symbol=body.symbol,
        exchange=body.exchange,
        side=body.side,
        quantity=body.quantity,
        amount=body.amount,
    )


@app.get("/api/trade/positions")
def trade_positions(user: dict = Depends(get_current_user)):
    return {"positions": list_positions(user["id"])}


@app.get("/api/trade/orders")
def trade_orders(user: dict = Depends(get_current_user)):
    return {"orders": list_orders(user["id"])}


@app.get("/api/funds")
def funds_list(
    category: str | None = Query(None),
    q: str | None = Query(None),
    max_min_sip: float | None = Query(None),
):
    return list_funds(category=category, q=q, max_min_sip=max_min_sip)


@app.post("/api/funds/buy")
def funds_buy(body: MfBuyBody, user: dict = Depends(get_current_user)):
    return buy_lumpsum(user["id"], body.fund_id, body.amount)


@app.post("/api/funds/sip")
def funds_sip(body: MfSipBody, user: dict = Depends(get_current_user)):
    return create_sip(
        user["id"],
        body.fund_id,
        body.amount,
        body.frequency,
        invest_now=body.invest_now,
    )


@app.get("/api/funds/holdings")
def funds_holdings(user: dict = Depends(get_current_user)):
    return {"holdings": list_mf_holdings(user["id"])}


@app.get("/api/funds/sips")
def funds_sips(user: dict = Depends(get_current_user)):
    return {"sips": list_sips(user["id"])}


@app.post("/api/funds/sips/{sip_id}/pause")
def funds_sip_pause(sip_id: int, user: dict = Depends(get_current_user)):
    return pause_sip(user["id"], sip_id)


@app.get("/api/funds/{fund_id}")
def funds_get(fund_id: str):
    return get_fund(fund_id)


@app.get("/api/portfolio/overview")
def portfolio_overview(user: dict = Depends(get_current_user)):
    return portfolio_summary(user["id"])


@app.get("/api/portfolios")
def portfolios_list(
    user: dict = Depends(get_current_user),
    include_holdings: bool = Query(False, description="Include holdings for every portfolio"),
):
    if include_holdings:
        portfolios = list_portfolios_with_holdings(user["id"])
    else:
        portfolios = list_portfolios(user["id"])
    total_holdings = sum(portfolio.get("holding_count", 0) for portfolio in portfolios)
    return {
        "portfolios": portfolios,
        "summary": {
            "portfolio_count": len(portfolios),
            "holding_count": total_holdings,
        },
    }


@app.post("/api/portfolios")
def portfolios_create(body: PortfolioBody, user: dict = Depends(get_current_user)):
    return create_portfolio(user["id"], body.name)


@app.get("/api/portfolios/{portfolio_id}")
def portfolios_get(portfolio_id: int, user: dict = Depends(get_current_user)):
    return get_portfolio(user["id"], portfolio_id)


@app.delete("/api/portfolios/{portfolio_id}")
def portfolios_delete(portfolio_id: int, user: dict = Depends(get_current_user)):
    delete_portfolio(user["id"], portfolio_id)
    return {"ok": True}


@app.post("/api/portfolios/{portfolio_id}/holdings")
def portfolios_add_holding(
    portfolio_id: int,
    body: HoldingBody,
    user: dict = Depends(get_current_user),
):
    holding = add_holding(user["id"], portfolio_id, body.symbol, body.exchange)
    return {"holding": holding}


@app.delete("/api/portfolios/{portfolio_id}/holdings/{symbol}")
def portfolios_remove_holding(
    portfolio_id: int,
    symbol: str,
    user: dict = Depends(get_current_user),
):
    remove_holding(user["id"], portfolio_id, symbol)
    return {"ok": True}


@app.post("/api/concall/summarize")
def concall_summarize(body: ConcallSummaryBody):
    try:
        return _sanitize(summarize_concall_document(body.attachment_url, body.subject))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


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
    """Replace NaN/Inf and numpy scalars so JSON serialization doesn't fail."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, tuple):
        return [_sanitize(v) for v in obj]
    # numpy.bool_, numpy.int64, numpy.float64, etc.
    if hasattr(obj, "item") and callable(obj.item) and type(obj).__module__ == "numpy":
        return _sanitize(obj.item())
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, bool):
        return bool(obj)
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


def _build_data_warnings(
    indian_api: dict,
    disclosures: dict,
    last_bar_as_of: str,
    ohlcv_provider: str,
    synthetic_ohlc: bool,
) -> list[str]:
    warnings = []

    provenance = indian_api.get("provenance") or {}
    stale: list[tuple[str, int]] = []
    rate_limited: list[str] = []
    failed: list[str] = []
    for name, meta in provenance.items():
        if not isinstance(meta, dict):
            continue
        status = meta.get("status")
        if status == "stale_cache":
            stale.append((name, int(meta.get("cache_age_seconds") or 0)))
        elif status in ("ok", None):
            continue
        elif meta.get("http_status") == 429:
            rate_limited.append(name)
        else:
            failed.append(name)

    if stale:
        oldest = max(age for _, age in stale)
        warnings.append(
            f"{len(stale)} data feed(s) served from cache because IndianAPI was unreachable "
            f"({', '.join(sorted(name for name, _ in stale))}). "
            f"Oldest cached value is {_format_age(oldest)} old — figures may have moved since."
        )
    if rate_limited:
        warnings.append(
            "IndianAPI rate limit hit and no cached copy exists yet — "
            f"{len(rate_limited)} data feed(s) could not load ({', '.join(sorted(rate_limited))}). "
            "Sections that depend on them will look empty until the quota resets."
        )
    if failed:
        warnings.append(
            f"IndianAPI returned errors for: {', '.join(sorted(failed))}. Those sections are incomplete."
        )

    warnings.append(
        f"Technical indicators use completed {ohlcv_provider} candles, not an intraday candle."
    )
    if synthetic_ohlc:
        warnings.append(
            "IndianAPI history is close and volume only. Open/high/low are derived from consecutive closes, so candlestick patterns and ATR are approximate."
        )
    snapshot_status = (
        indian_api.get("provenance", {}).get("snapshot", {}).get("status")
    )
    if snapshot_status != "ok":
        warnings.append(
            "IndianAPI live snapshot is unavailable; displayed price falls back to the latest historical close."
        )
    if not indian_api.get("snapshot"):
        warnings.append("IndianAPI fundamental snapshot is unavailable.")
    filing_mode = (
        disclosures.get("provenance", {}).get("evidence_extraction")
        if isinstance(disclosures, dict)
        else None
    )
    if filing_mode == "metadata_only":
        warnings.append(
            "BSE filing PDF excerpts are loaded on demand; concall summaries still work from the filing list."
        )
    warnings.append(f"Latest technical-analysis candle: {last_bar_as_of}")
    return warnings


def _format_age(seconds: int) -> str:
    if seconds < 3600:
        return f"{max(1, seconds // 60)} min"
    if seconds < 86400:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} d"


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
