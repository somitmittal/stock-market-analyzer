"""Consolidated investment verdict — positives, negatives, and Buy/Hold/Sell."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from analysis.concall import NEGATIVE_TERMS, POSITIVE_TERMS
from analysis.institutional_technical import analyze_institutional_technicals


PHENOMENAL_THRESHOLD_PCT = 20.0
BULLISH_THEMES = {
    "AI & technology": (
        "software",
        "information technology",
        "it services",
        "semiconductor",
        "data center",
        "artificial intelligence",
    ),
    "Defence & aerospace": ("defence", "defense", "aerospace", "shipbuilding"),
    "Railways & infra": ("railway", "wagon", "locomotive", "infrastructure", "construction"),
    "Renewable energy": ("renewable", "solar", "wind", "green hydrogen", "power"),
    "Banking (rate cycle)": ("bank", "nbfc", "financial services"),
    "Capital goods / manufacturing": ("capital goods", "engineering", "industrial", "manufacturing"),
}

MACRO_RISK_RULES = (
    {
        "keywords": ("export", "overseas", "international", "us market", "europe"),
        "risks": (
            "US tariff / trade-war headlines can hurt export order visibility.",
            "China dumping or cheaper imports can pressure domestic pricing.",
        ),
    },
    {
        "keywords": ("steel", "metal", "aluminium", "mining", "commodity"),
        "risks": (
            "Global commodity swings and China export policy can compress margins.",
            "Geopolitical conflict can disrupt raw-material supply chains.",
        ),
    },
    {
        "keywords": ("software", "it services", "technology", "pharma"),
        "risks": (
            "US recession fears or slower client IT spending can delay deal wins.",
            "Currency moves (INR/USD) affect reported margins for exporters.",
        ),
    },
    {
        "keywords": ("oil", "gas", "energy", "refining", "petrochemical"),
        "risks": (
            "Crude-oil volatility and Middle-East tensions can swing profitability.",
        ),
    },
    {
        "keywords": ("auto", "vehicle", "tyre"),
        "risks": (
            "Weak consumer sentiment or higher interest rates can slow demand.",
        ),
    },
)

INDUSTRY_PE_BENCHMARKS: tuple[tuple[tuple[str, ...], float, float], ...] = (
    (("software", "information technology", "it services", "technology"), 22, 35),
    (("bank", "nbfc", "financial services"), 12, 18),
    (("pharma", "healthcare", "hospital", "drug"), 25, 40),
    (("fmcg", "consumer", "household"), 35, 55),
    (("metal", "steel", "mining", "aluminium"), 8, 15),
    (("oil", "gas", "energy", "power", "refining"), 8, 16),
    (("auto", "vehicle", "tyre"), 18, 30),
    (("defence", "defense", "aerospace"), 25, 45),
    (("railway", "infra", "construction", "engineering"), 20, 35),
    (("real estate", "realty", "property"), 18, 30),
)

MACRO_NEWS_TERMS = (
    ("us recession", "US slowdown / recession risk"),
    ("fed rate", "US Fed rate moves affecting global liquidity"),
    ("tariff", "Tariff / trade-war risk"),
    ("trade war", "Trade-war escalation"),
    ("china dump", "China dumping / import competition"),
    ("dumping", "Anti-dumping or cheap import pressure"),
    ("war", "Geopolitical conflict risk"),
    ("conflict", "Geopolitical conflict risk"),
    ("sanction", "Sanctions impacting trade flows"),
    ("inflation", "Inflation keeping input costs elevated"),
    ("crude", "Crude-oil price volatility"),
)


def build_investment_verdict(
    df,
    research: dict[str, Any],
    news: list[dict],
    technical: dict[str, Any] | None = None,
    historical_stats: dict[str, Any] | None = None,
    current_price: float | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the investment decision summary across business, valuation, and price action."""
    context = _with_historical_stats(research, historical_stats or {})
    snapshot = snapshot or {}
    price = current_price if current_price is not None else float(df["Close"].iloc[-1])

    sections = {
        "business": _analyze_business(context),
        "quarterly_results": _analyze_quarterly(context),
        "balance_sheet": _analyze_balance_sheet(context),
        "valuation": _analyze_valuation(context, snapshot, price),
        "price_action": _analyze_price_action(df, context, price, snapshot),
        "technicals": _analyze_technicals(df, technical),
        "insider_buying": _analyze_insider_buying(context),
        "news_and_concalls": _analyze_news_and_concalls(context, news),
        "macro_risks": _analyze_macro(context, news),
    }

    company_name = (
        (research.get("company_profile") or {}).get("name")
        or snapshot.get("companyName")
        or ""
    )
    _enrich_section_summaries(sections, company_name, research, snapshot, price)
    verdict, confidence, rationale = _consolidate_verdict(sections, company_name, snapshot.get("ticker") or "")
    return {
        "recommendation": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "sections": sections,
    }


def _analyze_business(research: dict[str, Any]) -> dict[str, Any]:
    positives: list[str] = []
    negatives: list[str] = []
    industry = str((research.get("company_profile") or {}).get("industry") or "").lower()
    sector = research.get("sector_context") or {}
    moat = research.get("moat_evidence") or {}
    order_book = research.get("order_book") or {}
    guidance = research.get("management_guidance") or {}

    for theme, keywords in BULLISH_THEMES.items():
        if any(keyword in industry for keyword in keywords):
            positives.append(f"Operates in {theme}, a structurally favoured theme in the current market.")

    if sector.get("available"):
        status = sector.get("status")
        rel = sector.get("relative_strength_pct")
        if status == "leading":
            positives.append(
                f"Sector is leading the market ({rel:+.1f}% vs Nifty 50 over 3 months)."
            )
        elif status == "improving_relative":
            positives.append(f"Sector is gaining relative strength ({rel:+.1f}% vs Nifty 50).")
        elif status == "lagging":
            negatives.append(f"Sector is lagging the broader market ({rel:+.1f}% vs Nifty 50).")

    if moat.get("available"):
        positives.extend(moat.get("evidence", [])[:3])

    if order_book.get("available"):
        positives.append("Recent filings mention order-book / new-order wins.")
        for excerpt in (order_book.get("excerpts") or [])[:2]:
            positives.append(excerpt)

    if guidance.get("available"):
        positives.append("Management guidance / investor presentation filed recently.")
        for excerpt in (guidance.get("excerpts") or [])[:2]:
            if any(term in excerpt.lower() for term in ("capex", "capacity", "expansion", "guidance")):
                positives.append(excerpt)

    categories = (research.get("recent_disclosures") or {}).get("categories") or {}
    for record in categories.get("management_guidance", [])[:3]:
        text = " ".join(
            str(record.get(key) or "") for key in ("subject", "headline")
        ).lower()
        if any(term in text for term in ("capex", "capacity", "expansion", "greenfield", "brownfield")):
            positives.append(f"Expansion/capex signal in filing: {record.get('subject', 'Investor update')}")

    if not positives:
        negatives.append("Limited evidence of order-book strength, moat, or sector tailwinds.")

    assessment = "strong" if len(positives) >= 3 and len(negatives) <= 1 else (
        "weak" if len(negatives) > len(positives) else "moderate"
    )
    return _section("Business quality & visibility", assessment, positives, negatives)


def _analyze_quarterly(research: dict[str, Any]) -> dict[str, Any]:
    positives: list[str] = []
    negatives: list[str] = []
    growth = research.get("growth") or {}
    if not growth.get("available"):
        return _section(
            "Latest quarterly results",
            "unknown",
            [],
            ["Quarterly results data unavailable."],
        )

    historical = research.get("_quarterly_raw") or {}
    sales = historical.get("Sales") or {}
    profit = historical.get("Net Profit") or {}
    revenue_yoy = growth.get("revenue_yoy_pct")
    profit_yoy = growth.get("profit_yoy_pct")
    margin_chg = growth.get("operating_margin_yoy_change_pp")
    sales_qoq = _latest_qoq(sales)
    profit_qoq = _latest_qoq(profit)
    period = growth.get("latest_period") or "latest quarter"

    if revenue_yoy is not None:
        msg = f"Revenue YoY ({period}): {revenue_yoy:+.1f}%."
        if revenue_yoy >= PHENOMENAL_THRESHOLD_PCT:
            positives.append(msg)
        else:
            negatives.append(msg + " Below phenomenal threshold.")
    if profit_yoy is not None:
        (positives if profit_yoy >= PHENOMENAL_THRESHOLD_PCT else negatives).append(
            f"Profit YoY ({period}): {profit_yoy:+.1f}%."
        )
    if sales_qoq is not None:
        (positives if sales_qoq >= PHENOMENAL_THRESHOLD_PCT else negatives).append(
            f"Revenue QoQ: {sales_qoq:+.1f}%."
        )
    if profit_qoq is not None:
        (positives if profit_qoq >= PHENOMENAL_THRESHOLD_PCT else negatives).append(
            f"Profit QoQ: {profit_qoq:+.1f}%."
        )
    if margin_chg is not None:
        (positives if margin_chg > 0 else negatives).append(
            f"Operating margin YoY change: {margin_chg:+.2f} pp."
        )

    phenomenal = (
        (revenue_yoy or 0) >= PHENOMENAL_THRESHOLD_PCT
        and (profit_yoy or 0) >= PHENOMENAL_THRESHOLD_PCT
        and (sales_qoq or 0) >= PHENOMENAL_THRESHOLD_PCT
        and (profit_qoq or 0) >= PHENOMENAL_THRESHOLD_PCT
        and (margin_chg or 0) > 0
    )
    ok = (
        (revenue_yoy or 0) > 0
        and (profit_yoy or 0) > 0
    )

    if phenomenal:
        assessment = "phenomenal"
        positives.insert(0, "Phenomenal quarter: >20% YoY and QoQ growth in sales & profit with margin expansion.")
    elif ok:
        assessment = "ok"
        if not phenomenal:
            negatives.append("Growth is positive but not phenomenal (>20–25% YoY & QoQ with margin expansion).")
    else:
        assessment = "weak"
        negatives.append("Latest quarter does not show healthy double-digit growth.")

    return _section("Latest quarterly results", assessment, positives, negatives)


def _analyze_balance_sheet(research: dict[str, Any]) -> dict[str, Any]:
    positives: list[str] = []
    negatives: list[str] = []
    cash = research.get("cash_quality") or {}
    balance = research.get("balance_sheet") or {}
    ownership = research.get("ownership") or {}
    pledging = ownership.get("pledging") or {}

    if cash.get("available"):
        if (cash.get("operating_cash_flow_latest") or 0) > 0:
            positives.append("Operating cash flow is positive.")
        else:
            negatives.append("Operating cash flow is negative.")
        if (cash.get("free_cash_flow_latest") or 0) > 0:
            positives.append("Free cash flow is positive.")
        elif cash.get("free_cash_flow_latest") is not None:
            negatives.append("Free cash flow is negative.")
        conversion = cash.get("cash_profit_conversion")
        if conversion is not None and conversion >= 0.8:
            positives.append(f"Cash profit conversion is healthy ({conversion:.0%}).")
        elif conversion is not None and conversion < 0.5:
            negatives.append(f"Low cash profit conversion ({conversion:.0%}).")

    if balance.get("available"):
        if balance.get("borrowings_trend") == "rising":
            negatives.append("Borrowings are rising.")
        else:
            positives.append("Borrowings are not trending higher.")
        if balance.get("reserves_trend") == "rising":
            positives.append("Reserves are growing.")

    pledge_flagged = False
    if pledging.get("available"):
        for excerpt in pledging.get("excerpts") or []:
            lowered = excerpt.lower()
            if any(term in lowered for term in ("pledged", "pledge", "encumbered")):
                if any(term in lowered for term in ("no ", "nil", "zero", "not pledged", "unpledged")):
                    positives.append("Filing indicates minimal/no promoter pledge.")
                else:
                    negatives.append(f"Pledge concern in filing: {excerpt}")
                    pledge_flagged = True

    categories = (research.get("recent_disclosures") or {}).get("categories") or {}
    for record in categories.get("shareholding", [])[:2]:
        text = str(record.get("subject") or "").lower()
        if "pledge" in text or "encumbrance" in text:
            if any(term in text for term in ("nil", "no pledge", "unpledged")):
                positives.append("Recent shareholding filing suggests no promoter pledge.")
            else:
                negatives.append(f"Shareholding filing mentions pledge/encumbrance: {record.get('subject')}")
                pledge_flagged = True

    clean = len(negatives) == 0 or (len(positives) > len(negatives) and not pledge_flagged)
    assessment = "clean" if clean and not pledge_flagged else (
        "risky" if pledge_flagged or len(negatives) >= 3 else "moderate"
    )
    return _section("Balance sheet & cash flows", assessment, positives, negatives)


def _analyze_technicals(df, technical: dict[str, Any] | None) -> dict[str, Any]:
    return analyze_institutional_technicals(df, technical)


def _analyze_insider_buying(research: dict[str, Any]) -> dict[str, Any]:
    positives: list[str] = []
    negatives: list[str] = []
    ownership = research.get("ownership") or {}
    if not ownership.get("available"):
        return _section(
            "Insider / institutional buying",
            "unknown",
            [],
            ["Shareholding trend data unavailable."],
        )

    promoter_trend = ownership.get("promoter_holding_trend")
    promoter = ownership.get("promoter_holding_latest_pct")
    fii = ownership.get("fii_holding_latest_pct")
    dii = ownership.get("dii_holding_latest_pct")

    if promoter is not None:
        positives.append(f"Promoter holding: {promoter:.2f}%.")
    if promoter_trend == "rising":
        positives.append("Promoter holding increased recently — strong insider confidence signal.")
    elif promoter_trend == "falling":
        negatives.append("Promoter holding has declined — monitor closely.")

    historical = research.get("_shareholding_raw") or {}
    fii_trend = _holding_trend(historical.get("FIIs") or {})
    dii_trend = _holding_trend(historical.get("DIIs") or {})
    if fii_trend == "rising":
        positives.append(f"FII holding rising (now {fii:.2f}%)." if fii else "FII holding is rising.")
    elif fii_trend == "falling":
        negatives.append(f"FII holding falling (now {fii:.2f}%)." if fii else "FII holding is falling.")
    if dii_trend == "rising":
        positives.append(f"DII holding rising (now {dii:.2f}%)." if dii else "DII holding is rising.")
    elif dii_trend == "falling":
        negatives.append(f"DII holding falling (now {dii:.2f}%)." if dii else "DII holding is falling.")

    buying_signals = sum(
        1 for trend in (promoter_trend, fii_trend, dii_trend) if trend == "rising"
    )
    assessment = "positive" if buying_signals >= 2 else (
        "negative" if sum(1 for t in (promoter_trend, fii_trend, dii_trend) if t == "falling") >= 2
        else "neutral"
    )
    return _section("Insider / institutional buying", assessment, positives, negatives)


def _analyze_news_and_concalls(research: dict[str, Any], news: list[dict]) -> dict[str, Any]:
    positives: list[str] = []
    negatives: list[str] = []
    categories = (research.get("recent_disclosures") or {}).get("categories") or {}
    filing_texts: list[str] = []

    for bucket in ("concall", "management_guidance"):
        for record in categories.get(bucket, [])[:3]:
            filing_texts.append(
                " ".join(str(record.get(key) or "") for key in ("subject", "headline"))
            )

    combined = " ".join(filing_texts)
    for term in POSITIVE_TERMS:
        if term in combined.lower():
            positives.append(f"Filing tone: '{term}' mentioned in recent concall/presentation.")
    for term in NEGATIVE_TERMS:
        if term in combined.lower():
            negatives.append(f"Filing tone: '{term}' mentioned in recent concall/presentation.")

    if filing_texts:
        positives.append(f"Latest filing: {filing_texts[0][:140]}…" if len(filing_texts[0]) > 140 else f"Latest filing: {filing_texts[0]}")

    for article in (news or [])[:8]:
        title = str(article.get("title") or "")
        lowered = title.lower()
        if any(term in lowered for term in POSITIVE_TERMS):
            positives.append(title)
        elif any(term in lowered for term in NEGATIVE_TERMS):
            negatives.append(title)

    positives = _dedupe(positives)[:6]
    negatives = _dedupe(negatives)[:6]

    assessment = "positive" if len(positives) > len(negatives) else (
        "negative" if len(negatives) > len(positives) else "mixed"
    )
    return _section("News & concalls", assessment, positives, negatives)


def _analyze_valuation(
    research: dict[str, Any],
    snapshot: dict[str, Any],
    current_price: float,
) -> dict[str, Any]:
    positives: list[str] = []
    negatives: list[str] = []
    valuation = research.get("valuation") or {}
    growth = research.get("growth") or {}
    industry = str((research.get("company_profile") or {}).get("industry") or "").lower()

    pe = valuation.get("pe")
    pb = valuation.get("pb") or valuation.get("price_to_book")
    peg = valuation.get("peg")
    eps_growth = valuation.get("eps_growth_pct") or growth.get("profit_yoy_pct")
    revenue_growth = growth.get("revenue_yoy_pct")

    if pe is not None:
        low, high = _industry_pe_range(industry)
        if pe < low:
            positives.append(f"Trailing P/E of {pe:.1f}x is below the typical {low:.0f}–{high:.0f}x industry range.")
        elif pe > high:
            negatives.append(f"Trailing P/E of {pe:.1f}x is above the typical {low:.0f}–{high:.0f}x industry range.")
        else:
            positives.append(f"Trailing P/E of {pe:.1f}x is within the typical industry band ({low:.0f}–{high:.0f}x).")

    if pb is not None:
        if pb < 3:
            positives.append(f"Price-to-book: {pb:.2f}x.")
        else:
            negatives.append(f"Price-to-book at {pb:.2f}x reflects a premium to book value.")

    high_growth = (
        (revenue_growth or 0) >= PHENOMENAL_THRESHOLD_PCT
        or (eps_growth or 0) >= PHENOMENAL_THRESHOLD_PCT
    )
    if peg is not None:
        if peg < 1.2:
            positives.append(f"PEG of {peg:.2f} suggests growth justifies the earnings multiple.")
        elif peg > 2.5:
            negatives.append(f"PEG of {peg:.2f} is rich — valuation demands flawless execution.")
    elif high_growth and pe is not None and pe > _industry_pe_range(industry)[1]:
        positives.append(
            "Valuation looks stretched on P/E alone, but high growth visibility can support a premium multiple."
        )
    elif pe is not None and not high_growth and pe > _industry_pe_range(industry)[1]:
        negatives.append("Premium valuation without matching growth — harder to justify at current levels.")

    forward = _forward_fy_valuation(pe, current_price, eps_growth, research)
    for item in forward.get("projections", []):
        positives.append(
            f"{item['fy']}: implied value ₹{item['implied_value']:.0f} "
            f"at current P/E on projected EPS ₹{item['projected_eps']:.1f}."
        )
    for note in forward.get("guidance_notes", []):
        positives.append(note)

    assessment = "attractive" if len(positives) > len(negatives) + 1 else (
        "expensive" if len(negatives) > len(positives) else "fair"
    )
    if high_growth and assessment == "expensive":
        assessment = "growth_premium"
    return _section("Valuation vs peers & forward FY", assessment, positives, negatives)


def _analyze_price_action(
    df,
    research: dict[str, Any],
    current_price: float,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    positives: list[str] = []
    negatives: list[str] = []
    close = df["Close"]
    returns = _price_returns(close)
    year_high = _to_float(snapshot.get("yearHigh")) or float(close.tail(252).max())
    year_low = _to_float(snapshot.get("yearLow")) or float(close.tail(252).min())

    pct_from_high = ((current_price - year_high) / year_high * 100) if year_high else None
    pct_from_low = ((current_price - year_low) / year_low * 100) if year_low else None

    for label, value in returns.items():
        if value is None:
            continue
        direction = "risen" if value > 0 else "fallen"
        (positives if value > 0 else negatives).append(
            f"Price has {direction} {abs(value):.1f}% over the last {label}."
        )

    business_ok = _business_fundamentals_intact(research)
    quarterly = research.get("growth") or {}
    phenomenal = quarterly.get("available") and (
        (quarterly.get("revenue_yoy_pct") or 0) >= PHENOMENAL_THRESHOLD_PCT
        and (quarterly.get("profit_yoy_pct") or 0) >= PHENOMENAL_THRESHOLD_PCT
    )

    if pct_from_high is not None and pct_from_high <= -20:
        if business_ok or phenomenal:
            positives.append(
                "Sharp drawdown from the 52-week high, but business visibility and results still look intact — "
                "may be sentiment/noise rather than broken fundamentals. No need to panic if you own the story."
            )
        else:
            negatives.append(
                "Meaningful fall from highs alongside softer fundamentals — treat the decline as a warning, not a dip to ignore."
            )
    elif pct_from_high is not None and -10 < pct_from_high < 0:
        positives.append("Mild pullback from highs — normal consolidation if the business thesis is unchanged.")

    if pct_from_low is not None and pct_from_low >= 40:
        negatives.append(
            "Stock has rallied sharply from its 52-week low — consider booking partial profits or trimming if valuation is rich."
        )
    if pct_from_high is not None and pct_from_high >= -5:
        negatives.append(
            "Trading near 52-week highs — momentum is strong, but risk-reward for new buys is lower; partial profit booking is sensible."
        )

    if returns.get("3m") is not None and abs(returns["3m"]) < 8 and returns.get("1m") is not None and abs(returns["1m"]) < 5:
        positives.append(
            "Price is consolidating in a tight range — often a base-building phase if business prospects remain intact."
        )

    deterioration = research.get("fundamental_deterioration") or {}
    if deterioration.get("detected") and pct_from_high is not None and pct_from_high < -15:
        negatives.append(
            "Price weakness is accompanied by fundamental deterioration flags — do not assume the tumble is purely temporary."
        )

    assessment = "buy_dip" if positives and business_ok and (pct_from_high or 0) <= -15 else (
        "trim" if any("profit" in n.lower() or "trim" in n.lower() for n in negatives) else (
            "consolidating" if "consolidating" in " ".join(positives).lower() else "neutral"
        )
    )
    return _section("Price action & profit booking", assessment, positives, negatives)


def _analyze_macro(research: dict[str, Any], news: list[dict]) -> dict[str, Any]:
    positives: list[str] = []
    negatives: list[str] = []
    industry = str((research.get("company_profile") or {}).get("industry") or "").lower()
    description = str((research.get("company_profile") or {}).get("description") or "").lower()
    context = f"{industry} {description}"

    for rule in MACRO_RISK_RULES:
        if any(keyword in context for keyword in rule["keywords"]):
            negatives.extend(rule["risks"])

    news_blob = " ".join(str(item.get("title") or "") for item in (news or [])[:12]).lower()
    for term, label in MACRO_NEWS_TERMS:
        if term in news_blob:
            negatives.append(f"Macro headline risk: {label}.")

    sector = research.get("sector_context") or {}
    if sector.get("available") and sector.get("status") in ("leading", "improving_relative"):
        positives.append("Sector relative strength suggests supportive domestic macro backdrop for this industry.")

    assessment = "low_risk" if not negatives else (
        "high_risk" if len(negatives) >= 3 else "moderate_risk"
    )
    return _section("Macro & external risks", assessment, positives, negatives)


def _enrich_section_summaries(
    sections: dict[str, dict],
    company_name: str,
    research: dict[str, Any],
    snapshot: dict[str, Any],
    current_price: float,
) -> None:
    """Attach one-line, stock-specific summaries so sections don't read as copy-paste."""
    growth = research.get("growth") or {}
    valuation = research.get("valuation") or {}
    ownership = research.get("ownership") or {}
    industry = (research.get("company_profile") or {}).get("industry") or snapshot.get("industry")

    if growth.get("available"):
        sections["quarterly_results"]["summary"] = (
            f"{company_name or 'Company'}: revenue YoY {growth.get('revenue_yoy_pct', 0):+.1f}%, "
            f"profit YoY {growth.get('profit_yoy_pct', 0):+.1f}% "
            f"({growth.get('latest_period') or 'latest quarter'})."
        )
    if valuation.get("pe") is not None:
        sections["valuation"]["summary"] = (
            f"P/E {valuation['pe']:.1f}x"
            + (f", PEG {valuation['peg']:.2f}" if valuation.get("peg") is not None else "")
            + (f" · {industry}" if industry else "")
            + f" · price ₹{current_price:,.2f}."
        )
    if ownership.get("available") and ownership.get("promoter_holding_latest_pct") is not None:
        sections["insider_buying"]["summary"] = (
            f"Promoter {ownership['promoter_holding_latest_pct']:.1f}%"
            + (f" ({ownership.get('promoter_holding_trend', 'flat')})" if ownership.get("promoter_holding_trend") else "")
            + (
                f"; FII {ownership['fii_holding_latest_pct']:.1f}%"
                if ownership.get("fii_holding_latest_pct") is not None
                else ""
            )
        )
    profile = research.get("company_profile") or {}
    if profile.get("industry"):
        sections["business"]["summary"] = f"{company_name or profile.get('name') or 'Company'} · {profile['industry']}."


def _consolidate_verdict(
    sections: dict[str, dict],
    company_name: str = "",
    symbol: str = "",
) -> tuple[str, str, str]:
    weights = {
        "business": 1.5,
        "quarterly_results": 1.5,
        "balance_sheet": 1.25,
        "valuation": 1.5,
        "price_action": 1.0,
        "technicals": 1.0,
        "insider_buying": 1.0,
        "news_and_concalls": 0.75,
        "macro_risks": 0.75,
    }
    positive_scores = {
        "strong": 2, "phenomenal": 2, "clean": 2, "bullish": 2, "positive": 2,
        "attractive": 2, "growth_premium": 1, "buy_dip": 2, "fair": 1,
        "low_risk": 1, "moderate": 1, "ok": 1, "neutral": 0, "mixed": 0,
        "consolidating": 1, "moderate_risk": -1, "expensive": -2, "trim": -1,
        "weak": -2, "risky": -2, "bearish": -2, "negative": -2, "high_risk": -2,
        "unknown": 0,
    }

    total = 0.0
    weight_sum = 0.0
    drivers: list[str] = []
    for key, section in sections.items():
        assessment = section.get("assessment", "unknown")
        score = positive_scores.get(assessment, 0)
        w = weights.get(key, 1.0)
        total += score * w
        weight_sum += w
        if score >= 2:
            drivers.append(f"+ {section.get('title')}: {assessment}")
        elif score <= -1:
            drivers.append(f"− {section.get('title')}: {assessment}")

    normalized = total / weight_sum if weight_sum else 0
    if normalized >= 0.9:
        verdict = "Buy"
    elif normalized <= -0.35:
        verdict = "Sell"
    else:
        verdict = "Hold"

    confidence = "high" if abs(normalized) >= 1.2 else ("medium" if abs(normalized) >= 0.5 else "low")

    label = company_name or symbol or "This stock"
    highlights: list[str] = []
    concerns: list[str] = []
    for key in (
        "quarterly_results",
        "valuation",
        "business",
        "price_action",
        "technicals",
        "insider_buying",
    ):
        section = sections.get(key) or {}
        summary = section.get("summary")
        if summary:
            highlights.append(summary)
        elif section.get("positives"):
            highlights.append(str(section["positives"][0]))
        if section.get("negatives"):
            concerns.append(str(section["negatives"][0]))

    rationale_parts = [f"{label} — {verdict} ({confidence} confidence)."]
    if highlights:
        rationale_parts.append("Strengths: " + " · ".join(_dedupe(highlights)[:3]))
    if concerns:
        rationale_parts.append("Risks: " + " · ".join(_dedupe(concerns)[:3]))
    elif drivers:
        rationale_parts.append("Key drivers: " + "; ".join(drivers[:3]) + ".")
    rationale = " ".join(rationale_parts)
    return verdict, confidence, rationale


def _with_historical_stats(
    research: dict[str, Any],
    historical_stats: dict[str, Any],
) -> dict[str, Any]:
    context = dict(research)
    context["_quarterly_raw"] = historical_stats.get("quarter_results") or {}
    context["_shareholding_raw"] = historical_stats.get("shareholding_pattern_quarterly") or {}
    return context


def _section(
    title: str,
    assessment: str,
    positives: list[str],
    negatives: list[str],
    summary: str | None = None,
) -> dict[str, Any]:
    result = {
        "title": title,
        "assessment": assessment,
        "positives": _dedupe(positives),
        "negatives": _dedupe(negatives),
    }
    if summary:
        result["summary"] = summary
    return result


def _latest_qoq(values: dict[str, Any]) -> float | None:
    ordered = list(values.values())
    if len(ordered) < 2:
        return None
    try:
        latest = float(ordered[-1])
        prior = float(ordered[-2])
    except (TypeError, ValueError):
        return None
    if prior == 0:
        return None
    return (latest - prior) / abs(prior) * 100


def _holding_trend(values: dict[str, Any]) -> str:
    ordered = []
    for value in values.values():
        try:
            ordered.append(float(value))
        except (TypeError, ValueError):
            continue
    if len(ordered) < 2:
        return "insufficient_history"
    if ordered[-1] > ordered[-2]:
        return "rising"
    if ordered[-1] < ordered[-2]:
        return "falling"
    return "flat"


def _industry_pe_range(industry: str) -> tuple[float, float]:
    for keywords, low, high in INDUSTRY_PE_BENCHMARKS:
        if any(keyword in industry for keyword in keywords):
            return low, high
    return 15.0, 25.0


def _forward_fy_valuation(
    pe: float | None,
    current_price: float,
    eps_growth_pct: float | None,
    research: dict[str, Any],
) -> dict[str, Any]:
    projections: list[dict[str, Any]] = []
    guidance_notes: list[str] = []

    guidance = research.get("management_guidance") or {}
    for excerpt in (guidance.get("excerpts") or [])[:3]:
        for match in re.finditer(r"fy\s*20?(\d{2})", excerpt, flags=re.IGNORECASE):
            guidance_notes.append(f"Management guidance references FY20{match.group(1)}: {excerpt[:120]}…")
        if re.search(r"revenue|sales|guidance|target|capex", excerpt, flags=re.IGNORECASE):
            guidance_notes.append(f"Guidance signal: {excerpt[:140]}…")

    categories = (research.get("recent_disclosures") or {}).get("categories") or {}
    for bucket in ("management_guidance", "concall"):
        for record in categories.get(bucket, [])[:2]:
            text = " ".join(str(record.get(key) or "") for key in ("subject", "headline"))
            for match in re.finditer(r"fy\s*20?(\d{2})", text, flags=re.IGNORECASE):
                guidance_notes.append(f"Filing mentions FY20{match.group(1)}: {text[:120]}…")

    if pe in (None, 0) or eps_growth_pct is None:
        return {"projections": projections, "guidance_notes": _dedupe(guidance_notes)[:4]}

    current_eps = current_price / pe
    growth = max(min(eps_growth_pct / 100, 0.6), -0.4)
    fy_start = datetime.now().year + 1 if datetime.now().month >= 4 else datetime.now().year
    for offset in (1, 2, 3):
        projected_eps = current_eps * ((1 + growth) ** offset)
        implied_value = projected_eps * pe
        projections.append(
            {
                "fy": f"FY{str(fy_start + offset)[-2:]}",
                "projected_eps": round(projected_eps, 2),
                "implied_value": round(implied_value, 2),
            }
        )

    return {"projections": projections, "guidance_notes": _dedupe(guidance_notes)[:4]}


def _price_returns(close) -> dict[str, float | None]:
    current = float(close.iloc[-1])
    windows = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
    returns: dict[str, float | None] = {}
    for label, days in windows.items():
        if len(close) <= days:
            returns[label] = None
            continue
        prior = float(close.iloc[-days])
        returns[label] = (current - prior) / prior * 100 if prior else None
    return returns


def _business_fundamentals_intact(research: dict[str, Any]) -> bool:
    deterioration = research.get("fundamental_deterioration") or {}
    growth = research.get("growth") or {}
    business = research.get("sector_context") or {}
    if deterioration.get("detected"):
        return False
    if growth.get("available") and (growth.get("profit_yoy_pct") or 0) < 0:
        return False
    return True


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = re.sub(r"\s+", " ", item.strip())
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result
