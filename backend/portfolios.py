"""Portfolio CRUD — requires authenticated user."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from db import get_conn, row_to_dict


def list_portfolios(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.created_at,
                   COUNT(h.id) AS holding_count
            FROM portfolios p
            LEFT JOIN portfolio_holdings h ON h.portfolio_id = p.id
            WHERE p.user_id = ?
            GROUP BY p.id
            ORDER BY p.created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def list_portfolios_with_holdings(user_id: int) -> list[dict[str, Any]]:
    """Return every portfolio with its holdings in one response."""
    portfolios = list_portfolios(user_id)
    if not portfolios:
        return []

    portfolio_ids = [portfolio["id"] for portfolio in portfolios]
    placeholders = ",".join("?" * len(portfolio_ids))
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT portfolio_id, id, symbol, exchange, added_at
            FROM portfolio_holdings
            WHERE portfolio_id IN ({placeholders})
            ORDER BY added_at DESC
            """,
            portfolio_ids,
        ).fetchall()

    holdings_by_portfolio: dict[int, list[dict[str, Any]]] = {
        portfolio_id: [] for portfolio_id in portfolio_ids
    }
    for row in rows:
        holding = row_to_dict(row)
        holdings_by_portfolio[holding["portfolio_id"]].append(holding)

    for portfolio in portfolios:
        portfolio["holdings"] = holdings_by_portfolio.get(portfolio["id"], [])
        portfolio["holding_count"] = len(portfolio["holdings"])

    return portfolios


def create_portfolio(user_id: int, name: str) -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Portfolio name is required")
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO portfolios (user_id, name) VALUES (?, ?)",
            (user_id, clean_name),
        )
        portfolio_id = cursor.lastrowid
        row = conn.execute(
            "SELECT id, name, created_at FROM portfolios WHERE id = ?",
            (portfolio_id,),
        ).fetchone()
    portfolio = row_to_dict(row) or {}
    portfolio["holdings"] = []
    portfolio["holding_count"] = 0
    return portfolio


def _get_owned_portfolio(user_id: int, portfolio_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, created_at FROM portfolios WHERE id = ? AND user_id = ?",
            (portfolio_id, user_id),
        ).fetchone()
    portfolio = row_to_dict(row)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


def get_portfolio(user_id: int, portfolio_id: int) -> dict[str, Any]:
    portfolio = _get_owned_portfolio(user_id, portfolio_id)
    with get_conn() as conn:
        holdings = conn.execute(
            """
            SELECT id, symbol, exchange, added_at
            FROM portfolio_holdings
            WHERE portfolio_id = ?
            ORDER BY added_at DESC
            """,
            (portfolio_id,),
        ).fetchall()
    portfolio["holdings"] = [row_to_dict(row) for row in holdings]
    portfolio["holding_count"] = len(portfolio["holdings"])
    return portfolio


def delete_portfolio(user_id: int, portfolio_id: int) -> None:
    _get_owned_portfolio(user_id, portfolio_id)
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM portfolios WHERE id = ? AND user_id = ?",
            (portfolio_id, user_id),
        )


def add_holding(
    user_id: int,
    portfolio_id: int,
    symbol: str,
    exchange: str = "NSE",
) -> dict[str, Any]:
    _get_owned_portfolio(user_id, portfolio_id)
    clean_symbol = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    clean_exchange = exchange.strip().upper()
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    with get_conn() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO portfolio_holdings (portfolio_id, symbol, exchange)
                VALUES (?, ?, ?)
                """,
                (portfolio_id, clean_symbol, clean_exchange),
            )
        except Exception:
            raise HTTPException(
                status_code=409,
                detail=f"{clean_symbol} is already in this portfolio",
            )
        row = conn.execute(
            "SELECT id, symbol, exchange, added_at FROM portfolio_holdings WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row) or {}


def remove_holding(user_id: int, portfolio_id: int, symbol: str) -> None:
    _get_owned_portfolio(user_id, portfolio_id)
    clean_symbol = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    with get_conn() as conn:
        result = conn.execute(
            """
            DELETE FROM portfolio_holdings
            WHERE portfolio_id = ? AND symbol = ?
            """,
            (portfolio_id, clean_symbol),
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Holding not found in portfolio")
