"""Mutual funds — Coin/Bachat-style explore + ₹100 SIPs (paper demo)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException

from db import get_conn, row_to_dict
from trading import ensure_wallet

MIN_SIP_AMOUNT = 100.0
MIN_LUMPSUM = 100.0

# Curated demo catalog. NAV/returns are illustrative for the paper platform.
FUND_CATALOG: list[dict[str, Any]] = [
    {
        "id": "nifty50-index",
        "name": "Nivesh Nifty 50 Index Fund",
        "amc": "Nivesh AMC",
        "category": "Index",
        "risk": "Moderate",
        "min_sip": 100,
        "min_lumpsum": 100,
        "expense_ratio": 0.18,
        "nav": 248.35,
        "returns_1y": 12.4,
        "returns_3y": 14.1,
        "returns_5y": 13.8,
        "score": 86,
        "tagline": "Track India's top 50 — simple, low-cost start from ₹100.",
        "highlights": ["Direct plan style", "No lock-in", "Ideal first SIP"],
    },
    {
        "id": "flexi-growth",
        "name": "Nivesh Flexi Cap Growth",
        "amc": "Nivesh AMC",
        "category": "Flexi Cap",
        "risk": "High",
        "min_sip": 100,
        "min_lumpsum": 500,
        "expense_ratio": 0.72,
        "nav": 96.12,
        "returns_1y": 18.6,
        "returns_3y": 16.9,
        "returns_5y": 15.2,
        "score": 82,
        "tagline": "One fund across large, mid & small caps.",
        "highlights": ["Diversified equity", "Active style", "SIP from ₹100"],
    },
    {
        "id": "insta-liquid",
        "name": "Nivesh Insta Liquid Fund",
        "amc": "Nivesh AMC",
        "category": "Liquid",
        "risk": "Low",
        "min_sip": 100,
        "min_lumpsum": 100,
        "expense_ratio": 0.15,
        "nav": 3421.08,
        "returns_1y": 6.8,
        "returns_3y": 6.4,
        "returns_5y": 5.9,
        "score": 91,
        "tagline": "Park idle cash — Bachat-style Instant Fund feel, withdraw anytime (demo).",
        "highlights": ["Low volatility", "Daily SIP ok", "Emergency stash"],
    },
    {
        "id": "gold-etf-fof",
        "name": "Nivesh Gold Savings FoF",
        "amc": "Nivesh AMC",
        "category": "Gold",
        "risk": "Moderate",
        "min_sip": 100,
        "min_lumpsum": 100,
        "expense_ratio": 0.45,
        "nav": 28.74,
        "returns_1y": 22.1,
        "returns_3y": 16.4,
        "returns_5y": 12.9,
        "score": 78,
        "tagline": "Gold exposure without making charges or GST on jewellery.",
        "highlights": ["Hedge", "SIP friendly", "No physical gold"],
    },
    {
        "id": "elss-tax",
        "name": "Nivesh Tax Saver ELSS",
        "amc": "Nivesh AMC",
        "category": "ELSS",
        "risk": "High",
        "min_sip": 500,
        "min_lumpsum": 500,
        "expense_ratio": 0.88,
        "nav": 64.5,
        "returns_1y": 15.2,
        "returns_3y": 17.8,
        "returns_5y": 16.1,
        "score": 80,
        "tagline": "Equity tax saver with 3-year lock-in (Section 80C).",
        "highlights": ["Tax benefit", "3y lock-in", "Long-term equity"],
    },
    {
        "id": "midcap-momentum",
        "name": "Nivesh Midcap Opportunities",
        "amc": "Nivesh AMC",
        "category": "Mid Cap",
        "risk": "High",
        "min_sip": 100,
        "min_lumpsum": 500,
        "expense_ratio": 0.95,
        "nav": 112.4,
        "returns_1y": 24.8,
        "returns_3y": 21.3,
        "returns_5y": 18.7,
        "score": 76,
        "tagline": "Higher growth potential with higher swings.",
        "highlights": ["Growth tilt", "Volatile", "Long horizon"],
    },
    {
        "id": "balanced-hybrid",
        "name": "Nivesh Balanced Advantage",
        "amc": "Nivesh AMC",
        "category": "Hybrid",
        "risk": "Moderate",
        "min_sip": 100,
        "min_lumpsum": 100,
        "expense_ratio": 0.65,
        "nav": 48.9,
        "returns_1y": 11.2,
        "returns_3y": 12.6,
        "returns_5y": 11.8,
        "score": 84,
        "tagline": "Equity + debt mix that adjusts with markets.",
        "highlights": ["Smoother ride", "Beginner friendly", "₹100 SIP"],
    },
    {
        "id": "silver-etf-fof",
        "name": "Nivesh Silver FoF",
        "amc": "Nivesh AMC",
        "category": "Silver",
        "risk": "High",
        "min_sip": 100,
        "min_lumpsum": 100,
        "expense_ratio": 0.5,
        "nav": 18.22,
        "returns_1y": 28.4,
        "returns_3y": 19.1,
        "returns_5y": None,
        "score": 72,
        "tagline": "Silver via mutual fund — no vault fees.",
        "highlights": ["Commodity", "SIP ok", "Volatile"],
    },
]


def list_funds(
    *,
    category: str | None = None,
    q: str | None = None,
    max_min_sip: float | None = None,
) -> dict[str, Any]:
    funds = list(FUND_CATALOG)
    if category:
        funds = [f for f in funds if f["category"].lower() == category.lower()]
    if q:
        needle = q.strip().lower()
        funds = [
            f
            for f in funds
            if needle in f["name"].lower()
            or needle in f["category"].lower()
            or needle in f["amc"].lower()
        ]
    if max_min_sip is not None:
        funds = [f for f in funds if f["min_sip"] <= max_min_sip]
    funds = sorted(funds, key=lambda f: (-f["score"], f["name"]))
    return {
        "funds": funds,
        "count": len(funds),
        "min_sip_platform": MIN_SIP_AMOUNT,
        "mode": "paper",
        "note": (
            "Demo mutual funds inspired by Coin & Bachat. "
            "Purchases use your virtual wallet — not real AMFI/AMC orders."
        ),
        "categories": sorted({f["category"] for f in FUND_CATALOG}),
    }


def get_fund(fund_id: str) -> dict[str, Any]:
    for fund in FUND_CATALOG:
        if fund["id"] == fund_id:
            return fund
    raise HTTPException(status_code=404, detail="Fund not found")


def _next_sip_date(frequency: str) -> str:
    today = date.today()
    freq = frequency.lower()
    if freq == "daily":
        nxt = today + timedelta(days=1)
    elif freq == "weekly":
        nxt = today + timedelta(days=7)
    elif freq == "monthly":
        month = today.month + 1
        year = today.year + (1 if month > 12 else 0)
        month = 1 if month > 12 else month
        day = min(today.day, 28)
        nxt = date(year, month, day)
    else:
        raise HTTPException(status_code=400, detail="frequency must be daily, weekly, or monthly")
    return nxt.isoformat()


def buy_lumpsum(user_id: int, fund_id: str, amount: float) -> dict[str, Any]:
    fund = get_fund(fund_id)
    if amount < fund["min_lumpsum"]:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum one-time investment is ₹{fund['min_lumpsum']:.0f}",
        )
    ensure_wallet(user_id)
    nav = float(fund["nav"])
    units = round(amount / nav, 4)

    with get_conn() as conn:
        wallet = conn.execute(
            "SELECT cash_balance FROM wallets WHERE user_id = ?", (user_id,)
        ).fetchone()
        cash = float(wallet["cash_balance"])
        if cash < amount:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient cash. Need ₹{amount:,.2f}, have ₹{cash:,.2f}",
            )
        conn.execute(
            "UPDATE wallets SET cash_balance = ?, updated_at = datetime('now') WHERE user_id = ?",
            (cash - amount, user_id),
        )
        holding = conn.execute(
            "SELECT id, units, invested_amount FROM mf_holdings WHERE user_id = ? AND fund_id = ?",
            (user_id, fund_id),
        ).fetchone()
        if holding:
            new_units = float(holding["units"]) + units
            new_invested = float(holding["invested_amount"]) + amount
            conn.execute(
                """
                UPDATE mf_holdings
                SET units = ?, invested_amount = ?, avg_nav = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (new_units, new_invested, new_invested / new_units, holding["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO mf_holdings (user_id, fund_id, units, invested_amount, avg_nav)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, fund_id, units, amount, nav),
            )
        cursor = conn.execute(
            """
            INSERT INTO mf_orders (user_id, fund_id, order_kind, amount, units, nav, status)
            VALUES (?, ?, 'lumpsum', ?, ?, ?, 'filled')
            """,
            (user_id, fund_id, amount, units, nav),
        )
        order_id = cursor.lastrowid

    return {
        "order_id": order_id,
        "fund": fund,
        "amount": amount,
        "units": units,
        "nav": nav,
        "kind": "lumpsum",
        "mode": "paper",
    }


def create_sip(
    user_id: int,
    fund_id: str,
    amount: float,
    frequency: str = "monthly",
    *,
    invest_now: bool = True,
) -> dict[str, Any]:
    fund = get_fund(fund_id)
    if amount < fund["min_sip"]:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum SIP for this fund is ₹{fund['min_sip']:.0f}",
        )
    if amount < MIN_SIP_AMOUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Platform minimum SIP is ₹{MIN_SIP_AMOUNT:.0f}",
        )

    first_order = None
    if invest_now:
        first_order = buy_lumpsum(user_id, fund_id, amount)

    next_date = _next_sip_date(frequency)
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO mf_sips (user_id, fund_id, amount, frequency, next_date, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            """,
            (user_id, fund_id, amount, frequency.lower(), next_date),
        )
        sip_id = cursor.lastrowid

    return {
        "sip_id": sip_id,
        "fund": fund,
        "amount": amount,
        "frequency": frequency.lower(),
        "next_date": next_date,
        "status": "active",
        "first_installment": first_order,
        "mode": "paper",
        "note": "UPI AutoPay is simulated. Installments debit your virtual wallet on next_date in a real product.",
    }


def list_sips(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM mf_sips
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    results = []
    for row in rows:
        item = row_to_dict(row) or {}
        try:
            item["fund"] = get_fund(item["fund_id"])
        except HTTPException:
            item["fund"] = {"id": item["fund_id"], "name": item["fund_id"]}
        results.append(item)
    return results


def pause_sip(user_id: int, sip_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM mf_sips WHERE id = ? AND user_id = ?",
            (sip_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="SIP not found")
        conn.execute(
            "UPDATE mf_sips SET status = 'paused' WHERE id = ?",
            (sip_id,),
        )
    return {**(row_to_dict(row) or {}), "status": "paused"}


def list_mf_holdings(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM mf_holdings
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    results = []
    for row in rows:
        item = row_to_dict(row) or {}
        fund = get_fund(item["fund_id"])
        units = float(item["units"])
        nav = float(fund["nav"])
        value = units * nav
        invested = float(item["invested_amount"])
        results.append(
            {
                **item,
                "fund": fund,
                "current_nav": nav,
                "value": round(value, 2),
                "pnl": round(value - invested, 2),
                "pnl_pct": round((value - invested) / invested * 100, 2) if invested else 0,
            }
        )
    return results


def portfolio_summary(user_id: int) -> dict[str, Any]:
    from trading import get_wallet, list_positions

    wallet = get_wallet(user_id)
    stocks = list_positions(user_id)
    funds = list_mf_holdings(user_id)
    mf_value = sum(f["value"] for f in funds)
    mf_invested = sum(f["invested_amount"] for f in funds)
    return {
        "wallet": wallet,
        "stocks": stocks,
        "mutual_funds": funds,
        "sips": list_sips(user_id),
        "summary": {
            "cash": wallet["cash_balance"],
            "stocks_value": wallet["holdings_value"],
            "mf_value": round(mf_value, 2),
            "total_value": round(wallet["cash_balance"] + wallet["holdings_value"] + mf_value, 2),
            "total_invested": round(wallet["invested_value"] + mf_invested, 2),
            "unrealized_pnl": round(
                wallet["unrealized_pnl"] + (mf_value - mf_invested),
                2,
            ),
        },
        "mode": "paper",
    }
