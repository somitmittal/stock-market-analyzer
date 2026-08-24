"""Evidence-based Indian equity research derived from structured disclosures."""

from __future__ import annotations

from datetime import datetime, time
from math import pow
from typing import Any
from zoneinfo import ZoneInfo


def analyze_company_research(
    snapshot: dict[str, Any] | None,
    historical_stats: dict[str, dict[str, Any] | None],
    market_history: dict[str, Any] | None = None,
    disclosures: dict[str, Any] | None = None,
    sector_rotation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = snapshot or {}
    disclosures = disclosures or {}
    metrics = _flatten_key_metrics(snapshot.get("keyMetrics") or {})
    quarterly = historical_stats.get("quarter_results") or {}
    cashflow = historical_stats.get("cashflow") or {}
    balance_sheet = historical_stats.get("balancesheet") or {}
    ratios = historical_stats.get("ratios") or {}
    shareholding = historical_stats.get("shareholding_pattern_quarterly") or {}

    growth = _growth_analysis(quarterly)
    cash_quality = _cash_quality_analysis(cashflow, quarterly)
    balance_sheet_analysis = _balance_sheet_analysis(balance_sheet)
    efficiency = _efficiency_analysis(metrics, ratios, cash_quality)
    filing_analysis = disclosures.get("analysis") or {}
    ownership = _ownership_analysis(
        snapshot.get("shareholding") or [],
        shareholding,
        filing_analysis.get("promoter_pledging"),
    )
    valuation = _valuation_analysis(metrics, growth)
    deterioration = _deterioration_flags(
        growth, cash_quality, balance_sheet_analysis, efficiency, ownership
    )
    moat_evidence = _moat_evidence(metrics, growth, efficiency)

    covered = sum(
        bool(section.get("available"))
        for section in (
            growth,
            cash_quality,
            balance_sheet_analysis,
            efficiency,
            ownership,
            valuation,
        )
    )

    return {
        "available": covered > 0,
        "data_coverage": {
            "available_sections": covered,
            "total_sections": 6,
        },
        "company_profile": {
            "name": snapshot.get("companyName"),
            "industry": snapshot.get("industry"),
            "description": (snapshot.get("companyProfile") or {}).get("companyDescription"),
        },
        "growth": growth,
        "cash_quality": cash_quality,
        "balance_sheet": balance_sheet_analysis,
        "management_efficiency": efficiency,
        "ownership": ownership,
        "valuation": valuation,
        "moat_evidence": moat_evidence,
        "fundamental_deterioration": {
            "detected": bool(deterioration),
            "flags": deterioration,
        },
        "sector_context": sector_rotation or {
            "available": False,
            "industry": snapshot.get("industry"),
        },
        "management_guidance": filing_analysis.get("management_guidance")
        or {"available": False},
        "order_book": filing_analysis.get("order_book") or {"available": False},
        "recent_disclosures": {
            "available": disclosures.get("available", False),
            "filing_window": disclosures.get("filing_window"),
            "announcement_count": disclosures.get("announcement_count", 0),
            "categories": disclosures.get("categories", {}),
            "provenance": disclosures.get("provenance"),
        },
        "genuine_volume": _genuine_volume_analysis(market_history or {}),
        "multibagger_scenarios": _multibagger_scenarios(),
    }


def _growth_analysis(quarterly: dict[str, Any]) -> dict[str, Any]:
    sales = quarterly.get("Sales") or {}
    profit = quarterly.get("Net Profit") or {}
    margin = quarterly.get("OPM %") or {}
    if not sales and not profit:
        return {"available": False}

    return {
        "available": True,
        "revenue_yoy_pct": _latest_yoy(sales),
        "profit_yoy_pct": _latest_yoy(profit),
        "operating_margin_latest_pct": _latest_value(margin),
        "operating_margin_yoy_change_pp": _latest_yoy_difference(margin),
        "latest_period": _latest_period(sales or profit),
    }


def _cash_quality_analysis(
    cashflow: dict[str, Any], quarterly: dict[str, Any]
) -> dict[str, Any]:
    cfo = cashflow.get("Cash from Operating Activity") or {}
    fcf = cashflow.get("Free Cash Flow") or {}
    cfo_op = cashflow.get("CFO/OP") or {}
    profit = quarterly.get("Net Profit") or {}
    if not cfo and not fcf:
        return {"available": False}

    cfo_latest = _latest_value(cfo)
    profit_latest = _latest_value(profit)
    return {
        "available": True,
        "operating_cash_flow_latest": cfo_latest,
        "free_cash_flow_latest": _latest_value(fcf),
        "cfo_to_operating_profit_latest": _latest_value(cfo_op),
        "cash_profit_conversion": (
            cfo_latest / profit_latest
            if cfo_latest is not None and profit_latest not in (None, 0)
            else None
        ),
        "operating_cash_flow_trend": _trend(cfo),
        "free_cash_flow_trend": _trend(fcf),
    }


def _balance_sheet_analysis(balance_sheet: dict[str, Any]) -> dict[str, Any]:
    borrowings = balance_sheet.get("Borrowings") or {}
    reserves = balance_sheet.get("Reserves") or {}
    if not borrowings and not reserves:
        return {"available": False}
    return {
        "available": True,
        "borrowings_latest": _latest_value(borrowings),
        "borrowings_trend": _trend(borrowings),
        "reserves_latest": _latest_value(reserves),
        "reserves_trend": _trend(reserves),
    }


def _efficiency_analysis(
    metrics: dict[str, float | None],
    ratios: dict[str, Any],
    cash_quality: dict[str, Any],
) -> dict[str, Any]:
    roce = ratios.get("ROCE %") or {}
    ccc = ratios.get("Cash Conversion Cycle") or {}
    roe = metrics.get("returnOnAverageEquity5YearAverage")
    roi = metrics.get("returnOnInvestmentMostRecentFiscalYear")
    if not roce and not ccc and roe is None and roi is None:
        return {"available": False}
    return {
        "available": True,
        "roe_5y_average_pct": roe,
        "return_on_investment_pct": roi,
        "roce_latest_pct": _latest_value(roce),
        "roce_trend": _trend(roce),
        "cash_conversion_cycle_latest_days": _latest_value(ccc),
        "cash_conversion_cycle_trend": _trend(ccc, lower_is_better=True),
        "cash_profit_conversion": cash_quality.get("cash_profit_conversion"),
    }


def _ownership_analysis(
    snapshot_shareholding: list[dict[str, Any]],
    history: dict[str, Any],
    promoter_pledging: dict[str, Any] | None = None,
) -> dict[str, Any]:
    promoters = history.get("Promoters") or {}
    fii = history.get("FIIs") or {}
    dii = history.get("DIIs") or {}

    if not promoters:
        for group in snapshot_shareholding:
            if "promoter" in str(group.get("categoryName", "")).lower():
                promoters = {
                    item.get("holdingDate"): item.get("percentage")
                    for item in group.get("categories", [])
                }
                break

    if not promoters and not fii and not dii and not (promoter_pledging or {}).get("available"):
        return {"available": False, "pledging": promoter_pledging or {"available": False}}
    return {
        "available": True,
        "promoter_holding_latest_pct": _latest_value(promoters),
        "promoter_holding_trend": _trend(promoters),
        "fii_holding_latest_pct": _latest_value(fii),
        "dii_holding_latest_pct": _latest_value(dii),
        "pledging": promoter_pledging or {"available": False},
    }


def _valuation_analysis(
    metrics: dict[str, float | None], growth: dict[str, Any]
) -> dict[str, Any]:
    pe = (
        metrics.get("pPerEBasicExcludingExtraordinaryItemsTTM")
        or metrics.get("pPerEExcludingExtraordinaryItemsMostRecentFiscalYear")
    )
    pb = metrics.get("priceToBookMostRecentFiscalYear")
    eps_growth = metrics.get("ePSGrowthRate5Year")
    if eps_growth is None:
        eps_growth = growth.get("profit_yoy_pct")
    peg = pe / eps_growth if pe is not None and eps_growth is not None and eps_growth > 0 else None
    if pe is None and pb is None and peg is None:
        return {"available": False}
    return {
        "available": True,
        "pe": pe,
        "price_to_book": pb,
        "eps_growth_pct": eps_growth,
        "peg": peg,
        "interpretation": (
            "PEG compares the current earnings multiple with measured earnings growth; "
            "it is not a standalone buy signal."
        ),
    }


def _moat_evidence(
    metrics: dict[str, float | None],
    growth: dict[str, Any],
    efficiency: dict[str, Any],
) -> dict[str, Any]:
    evidence = []
    if metrics.get("grossMargin5YearAverage") is not None:
        evidence.append(
            f"Five-year average gross margin: {metrics['grossMargin5YearAverage']:.2f}%"
        )
    if efficiency.get("roe_5y_average_pct") is not None:
        evidence.append(
            f"Five-year average ROE: {efficiency['roe_5y_average_pct']:.2f}%"
        )
    if efficiency.get("roce_latest_pct") is not None:
        evidence.append(f"Latest ROCE: {efficiency['roce_latest_pct']:.2f}%")
    if growth.get("operating_margin_yoy_change_pp") is not None:
        evidence.append(
            "Operating margin YoY change: "
            f"{growth['operating_margin_yoy_change_pp']:.2f} percentage points"
        )
    return {
        "available": bool(evidence),
        "evidence": evidence,
        "note": "Financial metrics are moat proxies; technology, brand and switching-cost claims require filings.",
    }


def _deterioration_flags(*sections: dict[str, Any]) -> list[str]:
    growth, cash_quality, balance_sheet, efficiency, ownership = sections
    flags = []
    if _is_negative(growth.get("revenue_yoy_pct")):
        flags.append("Revenue declined versus the comparable quarter.")
    if _is_negative(growth.get("profit_yoy_pct")):
        flags.append("Net profit declined versus the comparable quarter.")
    if _is_negative(growth.get("operating_margin_yoy_change_pp")):
        flags.append("Operating margin contracted versus the comparable quarter.")
    if _is_negative(cash_quality.get("operating_cash_flow_latest")):
        flags.append("Latest operating cash flow is negative.")
    if cash_quality.get("operating_cash_flow_trend") == "deteriorating":
        flags.append("Operating cash flow trend is deteriorating.")
    if balance_sheet.get("borrowings_trend") == "rising":
        flags.append("Borrowings are rising.")
    if efficiency.get("cash_conversion_cycle_trend") == "deteriorating":
        flags.append("Cash conversion cycle is deteriorating.")
    if ownership.get("promoter_holding_trend") == "falling":
        flags.append("Promoter holding is falling.")
    return flags


def _multibagger_scenarios() -> list[dict[str, Any]]:
    scenarios = []
    for multiple in (2, 3):
        for years in (3, 5):
            required_cagr = (pow(multiple, 1 / years) - 1) * 100
            scenarios.append(
                {
                    "multiple": f"{multiple}x",
                    "years": years,
                    "required_cagr_pct": round(required_cagr, 2),
                    "probability": None,
                    "note": "Probability requires a calibrated, out-of-sample model.",
                }
            )
    return scenarios


def _genuine_volume_analysis(market_history: dict[str, Any]) -> dict[str, Any]:
    datasets = market_history.get("datasets") or []
    volume_dataset = _dataset(datasets, "Volume")
    price_dataset = _dataset(datasets, "Price")
    volumes = volume_dataset.get("values", []) if volume_dataset else []
    prices = price_dataset.get("values", []) if price_dataset else []
    if not volumes:
        return {"available": False}

    latest = volumes[-1]
    latest_volume = _to_float(latest[1]) if len(latest) > 1 else None
    delivery = (
        _to_float(latest[2].get("delivery"))
        if len(latest) > 2 and isinstance(latest[2], dict)
        else None
    )
    prior_volumes = [
        _to_float(item[1]) for item in volumes[:-1] if len(item) > 1
    ]
    prior_volumes = [value for value in prior_volumes if value is not None]
    average_volume = (
        sum(prior_volumes) / len(prior_volumes) if prior_volumes else None
    )
    volume_ratio = (
        latest_volume / average_volume
        if latest_volume is not None and average_volume not in (None, 0)
        else None
    )
    price_change = _latest_change_pct(prices)

    as_of = str(latest[0]) if latest else None
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    partial_session = (
        as_of == now.date().isoformat() and now.time() < time(15, 30)
    )
    return {
        "available": True,
        "as_of": as_of,
        "partial_session": partial_session,
        "volume": latest_volume,
        "volume_vs_recent_average": volume_ratio,
        "delivery_pct": delivery,
        "price_change_pct": price_change,
        "interpretation": _volume_interpretation(
            price_change, volume_ratio, delivery, partial_session
        ),
    }


def _volume_interpretation(
    price_change: float | None,
    volume_ratio: float | None,
    delivery: float | None,
    partial_session: bool,
) -> str:
    if partial_session:
        return "Current-session volume is incomplete; do not compare it with full sessions yet."
    if price_change is None or volume_ratio is None:
        return "Insufficient data to validate participation."
    if price_change > 0:
        direction = "buying"
    elif price_change < 0:
        direction = "selling"
    else:
        direction = "flat"
    participation = "above recent average" if volume_ratio > 1 else "below recent average"
    delivery_note = (
        f" Delivery was {delivery:.1f}%." if delivery is not None else ""
    )
    return f"Price action indicates {direction} with volume {participation}.{delivery_note}"


def _dataset(datasets: list[dict[str, Any]], metric: str) -> dict[str, Any] | None:
    return next((item for item in datasets if item.get("metric") == metric), None)


def _latest_change_pct(prices: list[list[Any]]) -> float | None:
    if len(prices) < 2:
        return None
    latest_price = _to_float(prices[-1][1])
    prior_price = _to_float(prices[-2][1])
    if latest_price is None or prior_price in (None, 0):
        return None
    return (latest_price - prior_price) / abs(prior_price) * 100


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


def _latest_yoy(values: dict[str, Any]) -> float | None:
    ordered = list(values.values())
    if len(ordered) < 5:
        return None
    latest = _to_float(ordered[-1])
    prior = _to_float(ordered[-5])
    if latest is None or prior in (None, 0):
        return None
    return (latest - prior) / abs(prior) * 100


def _latest_yoy_difference(values: dict[str, Any]) -> float | None:
    ordered = list(values.values())
    if len(ordered) < 5:
        return None
    latest = _to_float(ordered[-1])
    prior = _to_float(ordered[-5])
    return latest - prior if latest is not None and prior is not None else None


def _latest_period(values: dict[str, Any]) -> str | None:
    return list(values.keys())[-1] if values else None


def _latest_value(values: dict[str, Any]) -> float | None:
    return _to_float(list(values.values())[-1]) if values else None


def _trend(values: dict[str, Any], lower_is_better: bool = False) -> str:
    ordered = [_to_float(value) for value in values.values()]
    ordered = [value for value in ordered if value is not None]
    if len(ordered) < 2:
        return "insufficient_history"
    rising = ordered[-1] > ordered[-2]
    if lower_is_better:
        return "improving" if not rising else "deteriorating"
    return "rising" if rising else "falling"


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_negative(value: Any) -> bool:
    number = _to_float(value)
    return number is not None and number < 0
