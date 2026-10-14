"""IndianAPI client with explicit provenance and failure metadata."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

import pandas as pd
import requests


DEFAULT_BASE_URL = "https://stock.indianapi.in"
REQUEST_TIMEOUT_SECONDS = 15
# Documented IndianAPI history windows. Daily TA needs ~200 bars for EMA200.
PERIOD_BY_INTERVAL = {"1d": "5yr", "1wk": "10yr", "1mo": "max"}
# Match product copy in main.py Yahoo 429 response ("wait 30 seconds").
RATE_LIMIT_COOLDOWN_SECONDS = 30
_STATS_NAMES = (
    "quarter_results",
    "cashflow",
    "balancesheet",
    "ratios",
    "shareholding_pattern_quarterly",
)
_SNAPSHOT_TTL = 300
_HISTORY_TTL = 300
_STATS_TTL = 21600
_TTL_BY_PATH = {"/historical_stats": _STATS_TTL, "/historical_data": _HISTORY_TTL}
_api_cache: dict[str, dict[str, Any]] = {}
_api_cache_lock = threading.Lock()
# Coalesce parallel callers (e.g. analyze OHLCV + research) onto one HTTP request.
_inflight: dict[str, dict[str, Any]] = {}
_inflight_lock = threading.Lock()
# After any 429, pause outbound IndianAPI calls so Markets/analyze don't stampede.
_rate_limited_until = 0.0
# Persisted so fetched data survives restarts instead of re-spending API quota.
_DISK_CACHE_DIR = Path(__file__).resolve().parent / ".api_cache"


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


def fetch_company_research(symbol: str, history_period: str = "5yr") -> dict[str, Any]:
    """Fetch snapshot, market history, and stats in parallel."""
    stats: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    tasks: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=len(_STATS_NAMES) + 2) as pool:
        tasks["snapshot"] = pool.submit(fetch_stock_snapshot, symbol)
        tasks["market_history"] = pool.submit(
            fetch_historical_market_data, symbol, history_period
        )
        for stats_name in _STATS_NAMES:
            tasks[stats_name] = pool.submit(fetch_historical_stats, symbol, stats_name)

        snapshot_result = tasks["snapshot"].result()
        market_history_result = tasks["market_history"].result()
        provenance["snapshot"] = snapshot_result["provenance"]
        provenance["market_history"] = market_history_result["provenance"]

        for stats_name in _STATS_NAMES:
            result = tasks[stats_name].result()
            stats[stats_name] = result["data"]
            provenance[stats_name] = result["provenance"]

    return {
        "snapshot": snapshot_result["data"],
        "market_history": market_history_result["data"],
        "historical_stats": stats,
        "provenance": provenance,
    }


def fundamentals_from_snapshot(snapshot: dict[str, Any] | None, symbol: str = "") -> dict[str, Any]:
    """Map IndianAPI snapshot metrics into the Yahoo-style fundamentals dict."""
    snapshot = snapshot or {}
    metrics = _flatten_key_metrics(snapshot.get("keyMetrics") or {})

    def metric(*keys: str) -> float | None:
        for key in keys:
            value = metrics.get(key)
            if value is not None:
                return value
        return None

    dividend = metric(
        "currentDividendYieldCommonStockPrimaryIssueLTM",
        "dividendYieldIndicatedAnnualDividendDividedByClosingprice",
        "dividendYield5YearAverage",
    )
    return {
        "company_name": snapshot.get("companyName") or symbol,
        "sector": "N/A",
        "industry": snapshot.get("industry", "N/A"),
        "market_cap": metric("marketCap"),
        "pe_ratio": metric(
            "pPerEBasicExcludingExtraordinaryItemsTTM",
            "pPerEIncludingExtraordinaryItemsTTM",
            "pPerEExcludingExtraordinaryItemsMostRecentFiscalYear",
        ),
        "forward_pe": None,
        "pb_ratio": metric(
            "priceToBookMostRecentFiscalYear",
            "priceToBookMostRecentQuarter",
        ),
        "dividend_yield": dividend / 100 if dividend is not None else None,
        "eps": metric(
            "ePSIncludingExtraOrdinaryItemsTrailing12Month",
            "eEPSExcludingExtraordinaryItemsMmostRecentFiscal yea",
        ),
        "revenue": None,
        "profit_margin": metric("netProfitMarginPercentTrailing12Month"),
        "operating_margin": metric("operatingMarginTrailing12Month"),
        "roe": metric("returnOnAverageEquity5YearAverage"),
        "roa": metric("returnOnAverageAssetsMostRecenFiscalYear"),
        "debt_to_equity": metric(
            "totalDebtPerTotalEquityMostRecentFiscalYear",
            "totalDebtPerTotalEquityMostRecentQuarter",
        ),
        "current_ratio": None,
        "quick_ratio": None,
        "free_cash_flow": metric(
            "freeCashFlowMostRecentFiscalYear",
            "freeCashFlowtrailing12Month",
        ),
        "earnings_growth": metric("growthRatePercentEPS3year", "ePSGrowthRate5Year"),
        "revenue_growth": metric(
            "growthRatePercentRevenue3Year",
            "revenueChangePercentTTMPOverTTM",
        ),
        "52_week_high": _to_float(snapshot.get("yearHigh")),
        "52_week_low": _to_float(snapshot.get("yearLow")),
        "50_day_avg": None,
        "200_day_avg": None,
        "beta": None,
        "short_ratio": None,
        "recommendation": None,
        "target_mean_price": None,
        "target_high_price": None,
        "target_low_price": None,
        "number_of_analysts": None,
    }


def _cache_get(key: str) -> dict[str, Any] | None:
    entry = _cache_entry(key)
    if entry and time.time() - entry["ts"] < entry["ttl"]:
        return entry["val"]
    return None


def _cache_entry(key: str) -> dict[str, Any] | None:
    """Return the cache entry regardless of freshness (memory first, then disk)."""
    with _api_cache_lock:
        entry = _api_cache.get(key)
    if entry is not None:
        return entry

    entry = _disk_cache_read(key)
    if entry is not None:
        with _api_cache_lock:
            _api_cache[key] = entry
    return entry


def _cache_set(key: str, value: dict[str, Any], ttl: int) -> None:
    entry = {"val": value, "ts": time.time(), "ttl": ttl}
    with _api_cache_lock:
        _api_cache[key] = entry
    _disk_cache_write(key, entry)


def _disk_cache_file(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return _DISK_CACHE_DIR / f"{digest}.json"


def _disk_cache_read(key: str) -> dict[str, Any] | None:
    path = _disk_cache_file(key)
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    if not isinstance(entry, dict) or "val" not in entry or "ts" not in entry:
        return None
    return entry


def _disk_cache_write(key: str, entry: dict[str, Any]) -> None:
    try:
        _DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _disk_cache_file(key)
        # Write via temp file so a crash cannot leave a half-written cache entry.
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({**entry, "key": key}))
        tmp.replace(path)
    except (OSError, TypeError, ValueError):
        pass


def _stale_cache_result(key: str, reason: dict[str, Any]) -> dict[str, Any] | None:
    """Serve expired cached data when the API call fails, flagged as stale."""
    entry = _cache_entry(key)
    if entry is None or entry.get("val") is None:
        return None
    cached = entry["val"]
    if not isinstance(cached, dict) or cached.get("data") is None:
        return None

    age_seconds = max(0, int(time.time() - entry["ts"]))
    provenance = {
        **(cached.get("provenance") or {}),
        **reason,
        "status": "stale_cache",
        "served_from_cache": True,
        "cache_age_seconds": age_seconds,
        "cached_at": datetime.fromtimestamp(entry["ts"], timezone.utc).isoformat(),
    }
    return {"data": cached["data"], "provenance": provenance}


def _cache_key(path: str, params: dict[str, str] | None) -> str:
    if not params:
        return path
    return f"{path}?{'&'.join(f'{k}={params[k]}' for k in sorted(params))}"


def _rate_limit_active() -> bool:
    return time.time() < _rate_limited_until


def _mark_rate_limited() -> None:
    global _rate_limited_until
    _rate_limited_until = time.time() + RATE_LIMIT_COOLDOWN_SECONDS


def _cooldown_result(path: str, cache_key: str, fetched_at: str) -> dict[str, Any]:
    failure = {
        "fetched_at": fetched_at,
        "endpoint": path,
        "http_status": 429,
        "error": f"IndianAPI cooldown active for {RATE_LIMIT_COOLDOWN_SECONDS}s after rate limit",
    }
    stale = _stale_cache_result(cache_key, failure)
    if stale is not None:
        return stale
    return {
        "data": None,
        "provenance": {
            "provider": "IndianAPI",
            "status": "error",
            **failure,
        },
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

    cache_key = _cache_key(path, params)
    ttl = _TTL_BY_PATH.get(path, _SNAPSHOT_TTL)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if _rate_limit_active():
        return _cooldown_result(path, cache_key, fetched_at)

    leader = False
    holder: dict[str, Any]
    with _inflight_lock:
        existing = _inflight.get(cache_key)
        if existing is None:
            holder = {"event": threading.Event(), "result": None}
            _inflight[cache_key] = holder
            leader = True
        else:
            holder = existing

    if not leader:
        holder["event"].wait(timeout=REQUEST_TIMEOUT_SECONDS + 5)
        if holder["result"] is not None:
            return holder["result"]
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        return {
            "data": None,
            "provenance": {
                "provider": "IndianAPI",
                "status": "error",
                "fetched_at": fetched_at,
                "endpoint": path,
                "error": "Coalesced request finished without a result",
            },
        }

    try:
        # Another request may have tripped the global cooldown while we waited to lead.
        if _rate_limit_active():
            result = _cooldown_result(path, cache_key, fetched_at)
            holder["result"] = result
            return result

        base_url = os.getenv("INDIAN_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        try:
            response = requests.get(
                f"{base_url}{path}",
                params=params,
                headers={"x-api-key": api_key, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            result = {
                "data": response.json(),
                "provenance": {
                    "provider": "IndianAPI",
                    "status": "ok",
                    "fetched_at": fetched_at,
                    "endpoint": path,
                },
            }
            _cache_set(cache_key, result, ttl)
            holder["result"] = result
            return result
        except requests.RequestException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code == 429:
                _mark_rate_limited()
            failure = {
                "fetched_at": fetched_at,
                "endpoint": path,
                "http_status": status_code,
                "error": str(exc),
            }
            stale = _stale_cache_result(cache_key, failure)
            result = stale or {
                "data": None,
                "provenance": {
                    "provider": "IndianAPI",
                    "status": "error",
                    **failure,
                },
            }
            holder["result"] = result
            return result
        except ValueError as exc:
            failure = {
                "fetched_at": fetched_at,
                "endpoint": path,
                "error": str(exc),
            }
            stale = _stale_cache_result(cache_key, failure)
            result = stale or {
                "data": None,
                "provenance": {
                    "provider": "IndianAPI",
                    "status": "invalid_response",
                    **failure,
                },
            }
            holder["result"] = result
            return result
    finally:
        holder["event"].set()
        with _inflight_lock:
            if _inflight.get(cache_key) is holder:
                _inflight.pop(cache_key, None)


def _flatten_key_metrics(sections: dict[str, Any]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for values in sections.values():
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            result[item["key"]] = _to_float(item.get("value"))
    return result


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "").replace(".BO", "")
