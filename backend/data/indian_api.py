"""IndianAPI client with explicit provenance and failure metadata."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests


DEFAULT_BASE_URL = "https://stock.indianapi.in"
REQUEST_TIMEOUT_SECONDS = 15
# Documented IndianAPI history windows. Daily TA needs ~200 bars for EMA200.
PERIOD_BY_INTERVAL = {"1d": "5yr", "1wk": "10yr", "1mo": "max"}


def _load_local_env() -> None:
    """Load the project .env for local development without extra dependencies."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_local_env()


def is_configured() -> bool:
    return bool(os.getenv("INDIAN_API_KEY"))


def fetch_stock_snapshot(symbol: str) -> dict[str, Any]:
    result = _get("/stock", params={"name": _clean_symbol(symbol)})
    data = result.get("data") or {}
    profile = data.get("companyProfile") if isinstance(data, dict) else {}
    if isinstance(profile, dict):
        result["provenance"]["provider_last_successful_refresh"] = profile.get(
            "lastSuccessfulRefresh"
        )
        result["provenance"]["provider_data_status"] = profile.get("dataStatus")
    return result


def fetch_historical_stats(symbol: str, stats: str) -> dict[str, Any]:
    return _get(
        "/historical_stats",
        params={"stock_name": _clean_symbol(symbol), "stats": stats},
    )


def fetch_historical_market_data(symbol: str, period: str = "1yr") -> dict[str, Any]:
    return _get(
        "/historical_data",
        params={"stock_name": _clean_symbol(symbol), "period": period, "filter": "price"},
    )


def history_to_ohlcv(market_history: dict[str, Any] | None, interval: str = "1d") -> pd.DataFrame:
    """Build OHLC bars from IndianAPI close+volume series.

    IndianAPI does not publish true high/low. Open is the prior close; high/low
    are the max/min of that open and close so indicators still have a range.
    """
    datasets = (market_history or {}).get("datasets") or []
    prices = _dataset_map(datasets, "Price")
    volumes = _dataset_map(datasets, "Volume")
    if not prices:
        return pd.DataFrame()

    rows = []
    previous_close: float | None = None
    for date_key in sorted(prices):
        close = prices[date_key]
        if close is None:
            continue
        open_price = previous_close if previous_close is not None else close
        high = max(open_price, close)
        low = min(open_price, close)
        volume = volumes.get(date_key) or 0.0
        rows.append(
            {
                "Date": pd.Timestamp(date_key),
                "Open": open_price,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume,
            }
        )
        previous_close = close

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("Date")
    if interval == "1wk":
        df = _resample_ohlcv(df, "W-FRI")
    elif interval == "1mo":
        df = _resample_ohlcv(df, "ME")
    df.attrs["ohlcv_provider"] = "IndianAPI"
    df.attrs["synthetic_ohlc"] = True
    return df


def _dataset_map(datasets: list[dict[str, Any]], metric: str) -> dict[str, float]:
    dataset = next((item for item in datasets if item.get("metric") == metric), None)
    if not dataset:
        return {}
    mapped: dict[str, float] = {}
    for item in dataset.get("values") or []:
        if not item:
            continue
        try:
            mapped[str(item[0])] = float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
    return mapped


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    resampled = df.resample(rule).agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    return resampled.dropna(subset=["Open", "High", "Low", "Close"])


def fetch_ipo_data() -> dict[str, Any]:
    return _get("/ipo")


def fetch_company_research(symbol: str) -> dict[str, Any]:
    snapshot_result = fetch_stock_snapshot(symbol)
    market_history_result = fetch_historical_market_data(symbol, period="1m")
    stats: dict[str, Any] = {}
    provenance: dict[str, Any] = {
        "snapshot": snapshot_result["provenance"],
        "market_history": market_history_result["provenance"],
    }
    for stats_name in (
        "quarter_results",
        "cashflow",
        "balancesheet",
        "ratios",
        "shareholding_pattern_quarterly",
    ):
        result = fetch_historical_stats(symbol, stats_name)
        stats[stats_name] = result["data"]
        provenance[stats_name] = result["provenance"]
    return {
        "snapshot": snapshot_result["data"],
        "market_history": market_history_result["data"],
        "historical_stats": stats,
        "provenance": provenance,
    }


def _get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    api_key = os.getenv("INDIAN_API_KEY")
    if not api_key:
        return {
            "data": None,
            "provenance": {
                "provider": "IndianAPI",
                "status": "not_configured",
                "fetched_at": fetched_at,
            },
        }

    base_url = os.getenv("INDIAN_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    try:
        response = requests.get(
            f"{base_url}{path}",
            params=params,
            headers={"x-api-key": api_key, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return {
            "data": response.json(),
            "provenance": {
                "provider": "IndianAPI",
                "status": "ok",
                "fetched_at": fetched_at,
                "endpoint": path,
            },
        }
    except requests.RequestException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        return {
            "data": None,
            "provenance": {
                "provider": "IndianAPI",
                "status": "error",
                "fetched_at": fetched_at,
                "endpoint": path,
                "http_status": status_code,
                "error": str(exc),
            },
        }
    except ValueError as exc:
        return {
            "data": None,
            "provenance": {
                "provider": "IndianAPI",
                "status": "invalid_response",
                "fetched_at": fetched_at,
                "endpoint": path,
                "error": str(exc),
            },
        }


def _clean_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "").replace(".BO", "")
