"""Three-month NSE sector relative-strength analysis."""

from __future__ import annotations

from typing import Any

from data.fetcher import get_stock_data


BENCHMARK = {"name": "Nifty 50", "symbol": "^NSEI"}
ROTATION_HORIZON = "3 months"

SECTOR_INDEXES = {
    "auto": {"name": "Nifty Auto", "symbol": "^CNXAUTO"},
    "bank": {"name": "Nifty Bank", "symbol": "^NSEBANK"},
    "energy": {"name": "Nifty Energy", "symbol": "^CNXENERGY"},
    "financial_services": {"name": "Nifty Financial Services", "symbol": "^CNXFINANCE"},
    "fmcg": {"name": "Nifty FMCG", "symbol": "^CNXFMCG"},
    "infrastructure": {"name": "Nifty Infrastructure", "symbol": "^CNXINFRA"},
    "it": {"name": "Nifty IT", "symbol": "^CNXIT"},
    "media": {"name": "Nifty Media", "symbol": "^CNXMEDIA"},
    "metal": {"name": "Nifty Metal", "symbol": "^CNXMETAL"},
    "pharma": {"name": "Nifty Pharma", "symbol": "^CNXPHARMA"},
    "realty": {"name": "Nifty Realty", "symbol": "^CNXREALTY"},
}

INDUSTRY_KEYWORDS = {
    "auto": ("auto", "automobile", "tyre", "vehicle"),
    "bank": ("bank",),
    "energy": ("energy", "oil", "gas", "power", "electricity", "renewable"),
    "financial_services": (
        "finance",
        "financial",
        "insurance",
        "asset management",
        "capital market",
    ),
    "fmcg": ("fmcg", "consumer staple", "household product", "personal care"),
    "infrastructure": (
        "infrastructure",
        "construction",
        "engineering",
        "logistics",
        "transport",
    ),
    "it": ("software", "information technology", "it services", "technology"),
    "media": ("media", "entertainment", "broadcast"),
    "metal": ("metal", "steel", "aluminium", "mining"),
    "pharma": ("pharma", "drug", "healthcare", "hospital", "biotech"),
    "realty": ("real estate", "realty", "property"),
}


def analyze_sector_rotation(industry: str | None) -> dict[str, Any]:
    sector_key = _resolve_sector(industry)
    if sector_key is None:
        return {
            "available": False,
            "industry": industry,
            "horizon": ROTATION_HORIZON,
            "note": "No NSE sector-index mapping was found for the reported industry.",
        }

    sector = SECTOR_INDEXES[sector_key]
    try:
        sector_prices = get_stock_data(sector["symbol"], period="3mo", interval="1d")
        benchmark_prices = get_stock_data(BENCHMARK["symbol"], period="3mo", interval="1d")
        sector_return = _period_return(sector_prices["Close"])
        benchmark_return = _period_return(benchmark_prices["Close"])
    except (ValueError, KeyError) as exc:
        return {
            "available": False,
            "industry": industry,
            "sector": sector,
            "horizon": ROTATION_HORIZON,
            "note": str(exc),
        }

    relative_return = sector_return - benchmark_return
    return {
        "available": True,
        "industry": industry,
        "horizon": ROTATION_HORIZON,
        "sector": sector,
        "benchmark": BENCHMARK,
        "sector_return_pct": round(sector_return, 2),
        "benchmark_return_pct": round(benchmark_return, 2),
        "relative_strength_pct": round(relative_return, 2),
        "status": _classify(sector_return, relative_return),
        "as_of": _as_of(sector_prices.index[-1]),
        "method": (
            "Sector index total price return minus Nifty 50 price return over the selected "
            "three-month horizon. This is relative strength, not proprietary MarketMojo scoring."
        ),
        "provenance": {
            "indices": "Official NSE index families",
            "historical_prices": "Yahoo Finance",
        },
    }


def _resolve_sector(industry: str | None) -> str | None:
    normalized = str(industry or "").lower()
    for sector, keywords in INDUSTRY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return sector
    return None


def _period_return(close) -> float:
    clean = close.dropna()
    if len(clean) < 2:
        raise ValueError("Insufficient sector-index history for the selected horizon.")
    start = float(clean.iloc[0])
    end = float(clean.iloc[-1])
    if start == 0:
        raise ValueError("Invalid zero starting value in sector-index history.")
    return (end - start) / abs(start) * 100


def _classify(sector_return: float, relative_return: float) -> str:
    if relative_return > 0 and sector_return > 0:
        return "leading"
    if relative_return > 0:
        return "improving_relative"
    if sector_return > 0:
        return "weakening_relative"
    return "lagging"


def _as_of(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
