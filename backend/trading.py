"""Paper trading — Zerodha-style amount/qty orders against a virtual wallet."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import time
from typing import Any

from fastapi import HTTPException

from db import get_conn, row_to_dict
from data.fetcher import (
    QUOTE_TTL,
    get_stock_data,
    resolve_indian_symbol,
    yfinance_enabled,
)

STARTING_CASH = 100_000.0
# Markets overview shares the quote TTL so refresh doesn't re-fanout 8 providers.
_MARKETS_TTL = QUOTE_TTL
_quote_cache: dict[str, dict[str, Any]] = {}
_quote_lock = threading.Lock()
_markets_cache: dict[str, Any] = {"ts": 0.0, "data": None}
_markets_lock = threading.Lock()


def ensure_wallet(user_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wallets WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return row_to_dict(row) or {}
        conn.execute(
            "INSERT INTO wallets (user_id, cash_balance) VALUES (?, ?)",
            (user_id, STARTING_CASH),
        )
        row = conn.execute("SELECT * FROM wallets WHERE user_id = ?", (user_id,)).fetchone()
    return row_to_dict(row) or {}


def get_wallet(user_id: int) -> dict[str, Any]:
    wallet = ensure_wallet(user_id)
    positions = list_positions(user_id)
    invested = sum(p["quantity"] * p["avg_price"] for p in positions)
    current = sum(p["quantity"] * p["ltp"] for p in positions)
    return {
        **wallet,
        "invested_value": round(invested, 2),
        "holdings_value": round(current, 2),
        "total_value": round(wallet["cash_balance"] + current, 2),
        "unrealized_pnl": round(current - invested, 2),
        "mode": "paper",
        "note": "Simulated wallet for learning. No real money moves.",
    }


def _quote_payload(
    resolved: str, exchange: str, close: float, change_pct: float
) -> dict[str, Any]:
    return {
        "symbol": resolved.upper().replace(".NS", "").replace(".BO", ""),
        "exchange": exchange.upper(),
        "yf_symbol": resolved.upper(),
        "ltp": round(close, 2),
        "change_pct": round(change_pct, 2),
        "available": True,
    }


def _quote_from_indian_snapshot(resolved: str, exchange: str) -> dict[str, Any] | None:
    """LTP from /stock snapshot — one light call, not 5yr /historical_data."""
    from data.indian_api import fetch_stock_snapshot, is_configured

    if not is_configured():
        return None
    result = fetch_stock_snapshot(resolved)
    if result.get("provenance", {}).get("status") not in ("ok", "stale_cache"):
        return None
    data = result.get("data") or {}
    prices = data.get("currentPrice") or {}
    close = None
    for key in (exchange.upper(), "NSE", "BSE"):
        if prices.get(key) is not None:
            try:
                close = float(prices[key])
                break
            except (TypeError, ValueError):
                continue
    if close is None:
        return None
    # Snapshot has no prior close; percentChange when IndianAPI provides it.
    raw_chg = data.get("percentChange")
    try:
        change_pct = float(raw_chg) if raw_chg is not None else 0.0
    except (TypeError, ValueError):
        change_pct = 0.0
    return _quote_payload(resolved, exchange, close, change_pct)


def get_quote(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    resolved = resolve_indian_symbol(symbol, exchange)
    cache_key = f"{resolved}:{exchange.upper()}"
    with _quote_lock:
        entry = _quote_cache.get(cache_key)
        if entry and time.time() - entry["ts"] < QUOTE_TTL:
            return entry["val"]

    last_error: Exception | None = None
    quote: dict[str, Any] | None = None

    # 1) Yahoo short bars when enabled (local / ENABLE_YFINANCE).
    if yfinance_enabled():
        try:
            df = get_stock_data(resolved, period="5d", interval="1d", prefer_yahoo=True)
            df = df.dropna(subset=["Close"])
            if not df.empty:
                close = float(df["Close"].iloc[-1])
                prev = float(df["Close"].iloc[-2]) if len(df) > 1 else close
                change_pct = ((close - prev) / prev * 100) if prev else 0
                quote = _quote_payload(resolved, exchange, close, change_pct)
        except Exception as exc:
            last_error = exc

    # 2) On Render (Yahoo off), use IndianAPI snapshot — never fan out 5yr history.
    if quote is None:
        try:
            quote = _quote_from_indian_snapshot(resolved, exchange)
        except Exception as exc:
            last_error = exc

    if quote is None:
        raise HTTPException(
            status_code=404,
            detail=f"Quote unavailable for {symbol}: {last_error or 'no price source'}",
        )

    with _quote_lock:
        _quote_cache[cache_key] = {"val": quote, "ts": time.time()}
        if len(_quote_cache) > 128:
            oldest = min(_quote_cache.items(), key=lambda item: item[1]["ts"])[0]
            _quote_cache.pop(oldest, None)
    return quote


def place_stock_order(
    user_id: int,
    *,
    symbol: str,
    exchange: str = "NSE",
    side: str,
    quantity: float | None = None,
    amount: float | None = None,
) -> dict[str, Any]:
    """Place a market order by quantity or rupee amount (Kite quick-order style)."""
    side = side.strip().upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")

    quote = get_quote(symbol, exchange)
    price = quote["ltp"]
    clean_symbol = quote["symbol"]

    if amount is not None and quantity is None:
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        quantity = round(amount / price, 4)
    if quantity is None or quantity <= 0:
        raise HTTPException(status_code=400, detail="Provide quantity or amount")

    notional = round(quantity * price, 2)
    ensure_wallet(user_id)

    with get_conn() as conn:
        wallet = conn.execute(
            "SELECT cash_balance FROM wallets WHERE user_id = ?", (user_id,)
        ).fetchone()
        cash = float(wallet["cash_balance"])
        position = conn.execute(
            """
            SELECT id, quantity, avg_price FROM stock_positions
            WHERE user_id = ? AND symbol = ? AND exchange = ?
            """,
            (user_id, clean_symbol, exchange.upper()),
        ).fetchone()

        if side == "BUY":
            if cash < notional:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient cash. Need ₹{notional:,.2f}, have ₹{cash:,.2f}",
                )
            new_cash = cash - notional
            if position:
                old_qty = float(position["quantity"])
                old_avg = float(position["avg_price"])
                new_qty = old_qty + quantity
                new_avg = (old_qty * old_avg + notional) / new_qty
                conn.execute(
                    """
                    UPDATE stock_positions
                    SET quantity = ?, avg_price = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (new_qty, new_avg, position["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO stock_positions (user_id, symbol, exchange, quantity, avg_price)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, clean_symbol, exchange.upper(), quantity, price),
                )
        else:
            if not position or float(position["quantity"]) < quantity:
                held = float(position["quantity"]) if position else 0
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough shares. Holding {held}, tried to sell {quantity}",
                )
            new_cash = cash + notional
            remaining = float(position["quantity"]) - quantity
            if remaining < 1e-8:
                conn.execute("DELETE FROM stock_positions WHERE id = ?", (position["id"],))
            else:
                conn.execute(
                    """
                    UPDATE stock_positions
                    SET quantity = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (remaining, position["id"]),
                )

        conn.execute(
            "UPDATE wallets SET cash_balance = ?, updated_at = datetime('now') WHERE user_id = ?",
            (new_cash, user_id),
        )
        cursor = conn.execute(
            """
            INSERT INTO stock_orders
            (user_id, symbol, exchange, side, order_type, quantity, price, amount, status)
            VALUES (?, ?, ?, ?, 'MARKET', ?, ?, ?, 'filled')
            """,
            (
                user_id,
                clean_symbol,
                exchange.upper(),
                side,
                quantity,
                price,
                notional,
            ),
        )
        order_id = cursor.lastrowid

    return {
        "order_id": order_id,
        "symbol": clean_symbol,
        "exchange": exchange.upper(),
        "side": side,
        "quantity": quantity,
        "price": price,
        "amount": notional,
        "status": "filled",
        "mode": "paper",
    }


def list_positions(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM stock_positions
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    results = []
    for row in rows:
        item = row_to_dict(row) or {}
        try:
            quote = get_quote(item["symbol"], item["exchange"])
            ltp = quote["ltp"]
            change_pct = quote["change_pct"]
        except HTTPException:
            ltp = float(item["avg_price"])
            change_pct = 0.0
        qty = float(item["quantity"])
        avg = float(item["avg_price"])
        value = qty * ltp
        invested = qty * avg
        results.append(
            {
                **item,
                "ltp": ltp,
                "change_pct": change_pct,
                "invested": round(invested, 2),
                "value": round(value, 2),
                "pnl": round(value - invested, 2),
                "pnl_pct": round((value - invested) / invested * 100, 2) if invested else 0,
            }
        )
    return results


def list_orders(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM stock_orders
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [row_to_dict(r) or {} for r in rows]


def list_watchlist(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM watchlist_items
            WHERE user_id = ?
            ORDER BY added_at DESC
            """,
            (user_id,),
        ).fetchall()
    results = []
    for row in rows:
        item = row_to_dict(row) or {}
        try:
            quote = get_quote(item["symbol"], item["exchange"])
            results.append({**item, **quote})
        except HTTPException:
            results.append({**item, "ltp": None, "change_pct": None, "available": False})
    return results


def add_watchlist(user_id: int, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    clean = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    with get_conn() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO watchlist_items (user_id, symbol, exchange)
                VALUES (?, ?, ?)
                """,
                (user_id, clean, exchange.upper()),
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"{clean} is already on your watchlist") from exc
        row = conn.execute(
            "SELECT * FROM watchlist_items WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    try:
        quote = get_quote(clean, exchange)
        return {**(row_to_dict(row) or {}), **quote}
    except HTTPException:
        return row_to_dict(row) or {}


def remove_watchlist(user_id: int, symbol: str, exchange: str = "NSE") -> None:
    clean = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    with get_conn() as conn:
        result = conn.execute(
            """
            DELETE FROM watchlist_items
            WHERE user_id = ? AND symbol = ? AND exchange = ?
            """,
            (user_id, clean, exchange.upper()),
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Watchlist item not found")


def market_overview() -> dict[str, Any]:
    """Popular NSE names for the Markets home — Zerodha marketwatch vibe."""
    with _markets_lock:
        cached = _markets_cache.get("data")
        if cached is not None and time.time() - float(_markets_cache["ts"]) < _MARKETS_TTL:
            return cached

    seeds = [
        ("RELIANCE", "NSE"),
        ("TCS", "NSE"),
        ("HDFCBANK", "NSE"),
        ("INFY", "NSE"),
        ("ICICIBANK", "NSE"),
        ("SBIN", "NSE"),
        ("BAJFINANCE", "NSE"),
        ("ITC", "NSE"),
    ]

    def _one(pair: tuple[str, str]) -> dict[str, Any]:
        symbol, exchange = pair
        try:
            return get_quote(symbol, exchange)
        except HTTPException:
            return {
                "symbol": symbol,
                "exchange": exchange,
                "ltp": None,
                "change_pct": None,
                "available": False,
            }

    with ThreadPoolExecutor(max_workers=min(4, len(seeds))) as pool:
        items = list(pool.map(_one, seeds))

    payload = {
        "watch": items,
        "yahoo_enabled": yfinance_enabled(),
        "note": "Live quotes via Yahoo Finance (preferred) with short-cache; IndianAPI reserved for research.",
        "cache_ttl_seconds": _MARKETS_TTL,
    }
    # Don't cache an all-empty watch — that locks Markets into "unavailable" for a full TTL.
    if any(item.get("available") for item in items):
        with _markets_lock:
            _markets_cache["data"] = payload
            _markets_cache["ts"] = time.time()
    return payload
