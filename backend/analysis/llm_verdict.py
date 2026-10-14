"""Gemini-powered investment verdict synthesis."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from analysis.gemini_client import generate_json, is_configured
from analysis.verdict import build_investment_verdict

SECTION_KEYS = (
    "business",
    "quarterly_results",
    "balance_sheet",
    "valuation",
    "price_action",
    "technicals",
    "insider_buying",
    "news_and_concalls",
    "macro_risks",
)

SECTION_TITLES = {
    "business": "Business quality & visibility",
    "quarterly_results": "Latest quarterly results",
    "balance_sheet": "Balance sheet & cash flows",
    "valuation": "Valuation vs peers & forward FY",
    "price_action": "Price action & profit booking",
    "technicals": "Institutional technical analysis",
    "insider_buying": "Insider / institutional buying",
    "news_and_concalls": "News & concalls",
    "macro_risks": "Macro & external risks",
}

SYSTEM_PROMPT = """You are a senior Indian equity research analyst writing for a serious retail investor.

Use ONLY the facts in the provided JSON context. Do not invent numbers, dates, or events.
If data is missing, say so explicitly in negatives — never guess.

Return strict JSON with this shape:
{
  "recommendation": "Buy" | "Hold" | "Sell",
  "confidence": "high" | "medium" | "low",
  "rationale": "2-4 sentences, stock-specific, citing actual metrics from context",
  "sections": {
    "business": {
      "assessment": "strong|moderate|weak",
      "summary": "one line",
      "positives": ["..."],
      "negatives": ["..."]
    },
    "quarterly_results": { "assessment": "phenomenal|ok|weak|unknown", ... },
    "balance_sheet": { "assessment": "clean|moderate|risky", ... },
    "valuation": { "assessment": "attractive|fair|expensive|growth_premium", ... },
    "price_action": { "assessment": "buy_dip|neutral|consolidating|trim", ... },
    "technicals": { "assessment": "bullish|neutral|bearish", ... },
    "insider_buying": { "assessment": "positive|neutral|negative|unknown", ... },
    "news_and_concalls": { "assessment": "positive|mixed|negative", ... },
    "macro_risks": { "assessment": "low_risk|moderate_risk|high_risk", ... }
  }
}

Each section needs 1-4 concise positives and 0-4 negatives grounded in the data.
Be direct about risks. Indian market context (NSE/BSE, promoter holding, FII/DII flows)."""


def build_llm_verdict(
    *,
    symbol: str,
    company_name: str,
    current_price: float,
    df: pd.DataFrame,
    research: dict[str, Any],
    news: list[dict],
    technical: dict[str, Any] | None,
    fundamentals: dict[str, Any],
    snapshot: dict[str, Any],
    historical_stats: dict[str, Any] | None = None,
    fallback_verdict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate verdict via Gemini; fall back to rule engine on failure."""
    if not is_configured():
        return _with_source(
            fallback_verdict
            or build_investment_verdict(
                df,
                research,
                news,
                technical,
                historical_stats=historical_stats,
                current_price=current_price,
                snapshot=snapshot,
            ),
            "rules",
        )

    fallback = fallback_verdict or build_investment_verdict(
        df,
        research,
        news,
        technical,
        historical_stats=historical_stats,
        current_price=current_price,
        snapshot=snapshot,
    )
    context = _build_context(
        symbol=symbol,
        company_name=company_name,
        current_price=current_price,
        df=df,
        research=research,
        news=news,
        technical=technical,
        fundamentals=fundamentals,
        snapshot=snapshot,
        rule_verdict=fallback,
    )
    try:
        raw = generate_json(
            SYSTEM_PROMPT,
            "Analyze this Indian stock using the framework. Context JSON:\n"
            + json.dumps(context, ensure_ascii=False),
        )
        return _with_source(_normalize_verdict(raw, fallback), "gemini")
    except Exception as exc:
        verdict = dict(fallback)
        verdict["analysis_error"] = str(exc)
        return _with_source(verdict, "rules")


def _build_context(
    *,
    symbol: str,
    company_name: str,
    current_price: float,
    df: pd.DataFrame,
    research: dict[str, Any],
    news: list[dict],
    technical: dict[str, Any] | None,
    fundamentals: dict[str, Any],
    snapshot: dict[str, Any],
    rule_verdict: dict[str, Any],
) -> dict[str, Any]:
    close = df["Close"]
    returns = {}
    for label, bars in (("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252)):
        if len(close) > bars:
            start = float(close.iloc[-bars - 1])
            end = float(close.iloc[-1])
            returns[label] = round((end - start) / start * 100, 2) if start else None

    tech = technical or {}
    ma = tech.get("moving_averages") or {}
    return {
        "symbol": symbol,
        "company_name": company_name,
        "current_price_inr": current_price,
        "industry": (research.get("company_profile") or {}).get("industry") or snapshot.get("industry"),
        "description": (research.get("company_profile") or {}).get("description"),
        "price_returns_pct": returns,
        "year_high": snapshot.get("yearHigh"),
        "year_low": snapshot.get("yearLow"),
        "growth": research.get("growth"),
        "valuation": research.get("valuation"),
        "cash_quality": research.get("cash_quality"),
        "balance_sheet": research.get("balance_sheet"),
        "ownership": research.get("ownership"),
        "sector_context": research.get("sector_context"),
        "fundamental_deterioration": research.get("fundamental_deterioration"),
        "management_guidance": research.get("management_guidance"),
        "order_book": research.get("order_book"),
        "recent_disclosures": research.get("recent_disclosures"),
        "fundamentals": {
            k: fundamentals.get(k)
            for k in (
                "pe_ratio",
                "pb_ratio",
                "market_cap",
                "dividend_yield",
                "roe",
                "revenue_growth",
                "earnings_growth",
                "52_week_high",
                "52_week_low",
            )
        },
        "technical_summary": {
            "trend": tech.get("trend"),
            "rsi": (tech.get("rsi") or {}).get("value"),
            "macd": tech.get("macd"),
            "adx": tech.get("adx"),
            "bollinger": tech.get("bollinger"),
            "moving_averages_overall": ma.get("overall"),
            "moving_average_cross": ma.get("cross"),
            "volume": tech.get("volume_analysis"),
            "support_resistance": tech.get("support_resistance"),
            "candlestick_patterns": tech.get("candlestick_patterns"),
        },
        "news_headlines": [
            {
                "title": item.get("title"),
                "publisher": item.get("publisher"),
                "published": item.get("published"),
            }
            for item in (news or [])[:10]
        ],
        "rule_based_hints": {
            "recommendation": rule_verdict.get("recommendation"),
            "rationale": rule_verdict.get("rationale"),
            "sections": {
                key: {
                    "assessment": (rule_verdict.get("sections") or {}).get(key, {}).get("assessment"),
                    "positives": ((rule_verdict.get("sections") or {}).get(key, {}) or {}).get("positives", [])[:3],
                    "negatives": ((rule_verdict.get("sections") or {}).get(key, {}) or {}).get("negatives", [])[:3],
                }
                for key in SECTION_KEYS
            },
        },
    }


def _normalize_verdict(raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    recommendation = str(raw.get("recommendation") or "").strip().title()
    if recommendation not in {"Buy", "Hold", "Sell"}:
        recommendation = fallback.get("recommendation", "Hold")

    confidence = str(raw.get("confidence") or "").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = fallback.get("confidence", "medium")

    rationale = str(raw.get("rationale") or "").strip() or fallback.get("rationale", "")
    sections_in = raw.get("sections") if isinstance(raw.get("sections"), dict) else {}
    fallback_sections = fallback.get("sections") or {}

    sections: dict[str, Any] = {}
    for key in SECTION_KEYS:
        section = sections_in.get(key) if isinstance(sections_in.get(key), dict) else {}
        fb = fallback_sections.get(key) or {}
        positives = _string_list(section.get("positives")) or _string_list(fb.get("positives"))
        negatives = _string_list(section.get("negatives")) or _string_list(fb.get("negatives"))
        sections[key] = {
            "title": SECTION_TITLES[key],
            "assessment": str(section.get("assessment") or fb.get("assessment") or "unknown"),
            "summary": str(section.get("summary") or fb.get("summary") or "").strip() or None,
            "positives": positives[:6],
            "negatives": negatives[:6],
        }
        if key == "technicals" and fb.get("vcp_detected") is not None:
            sections[key]["vcp_detected"] = bool(fb.get("vcp_detected"))

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "rationale": rationale,
        "sections": sections,
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _with_source(verdict: dict[str, Any], source: str) -> dict[str, Any]:
    result = dict(verdict)
    result["analysis_source"] = source
    return result
