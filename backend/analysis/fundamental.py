"""
Fundamental analysis module.
Evaluates company financials, valuation, growth, and financial health.
"""
from typing import Optional


def analyze_fundamentals(fundamentals: dict, balance_sheet: dict, income_stmt: dict) -> dict:
    """Run full fundamental analysis and return structured scores."""
    valuation = _analyze_valuation(fundamentals)
    profitability = _analyze_profitability(fundamentals)
    growth = _analyze_growth(fundamentals)
    financial_health = _analyze_financial_health(fundamentals, balance_sheet)
    analyst_sentiment = _analyze_analyst_sentiment(fundamentals)

    scores = [
        valuation["score"],
        profitability["score"],
        growth["score"],
        financial_health["score"],
        analyst_sentiment["score"],
    ]
    valid_scores = [s for s in scores if s is not None]
    overall_score = sum(valid_scores) / len(valid_scores) if valid_scores else 50

    overall_signal = "strong_buy" if overall_score >= 75 else \
                     "buy" if overall_score >= 60 else \
                     "hold" if overall_score >= 40 else \
                     "sell" if overall_score >= 25 else "strong_sell"

    return {
        "overall_score": round(overall_score, 1),
        "overall_signal": overall_signal,
        "valuation": valuation,
        "profitability": profitability,
        "growth": growth,
        "financial_health": financial_health,
        "analyst_sentiment": analyst_sentiment,
    }


def _analyze_valuation(f: dict) -> dict:
    signals = []
    score_components = []

    pe = f.get("pe_ratio")
    if pe is not None:
        if pe < 0:
            signals.append("Negative PE (company is unprofitable)")
            score_components.append(20)
        elif pe < 15:
            signals.append(f"PE of {pe:.1f} — undervalued territory")
            score_components.append(80)
        elif pe < 25:
            signals.append(f"PE of {pe:.1f} — fairly valued")
            score_components.append(60)
        elif pe < 40:
            signals.append(f"PE of {pe:.1f} — expensive")
            score_components.append(40)
        else:
            signals.append(f"PE of {pe:.1f} — very expensive")
            score_components.append(20)

    pb = f.get("pb_ratio")
    if pb is not None:
        if pb < 1:
            signals.append(f"P/B of {pb:.2f} — trading below book value")
            score_components.append(85)
        elif pb < 3:
            signals.append(f"P/B of {pb:.2f} — reasonable")
            score_components.append(60)
        else:
            signals.append(f"P/B of {pb:.2f} — premium valuation")
            score_components.append(35)

    fwd_pe = f.get("forward_pe")
    if fwd_pe is not None and pe is not None and fwd_pe > 0:
        if fwd_pe < pe:
            signals.append("Forward PE lower than trailing — earnings expected to grow")
            score_components.append(70)
        else:
            signals.append("Forward PE higher — earnings expected to decline")
            score_components.append(35)

    score = sum(score_components) / len(score_components) if score_components else None
    return {"score": round(score, 1) if score else None, "signals": signals}


def _analyze_profitability(f: dict) -> dict:
    signals = []
    score_components = []

    pm = f.get("profit_margin")
    if pm is not None:
        pm_pct = pm * 100
        if pm_pct > 20:
            signals.append(f"Excellent profit margin: {pm_pct:.1f}%")
            score_components.append(90)
        elif pm_pct > 10:
            signals.append(f"Good profit margin: {pm_pct:.1f}%")
            score_components.append(70)
        elif pm_pct > 0:
            signals.append(f"Thin profit margin: {pm_pct:.1f}%")
            score_components.append(45)
        else:
            signals.append(f"Negative margin: {pm_pct:.1f}%")
            score_components.append(15)

    roe = f.get("roe")
    if roe is not None:
        roe_pct = roe * 100
        if roe_pct > 20:
            signals.append(f"Strong ROE: {roe_pct:.1f}%")
            score_components.append(85)
        elif roe_pct > 10:
            signals.append(f"Decent ROE: {roe_pct:.1f}%")
            score_components.append(60)
        else:
            signals.append(f"Low ROE: {roe_pct:.1f}%")
            score_components.append(30)

    om = f.get("operating_margin")
    if om is not None:
        om_pct = om * 100
        if om_pct > 25:
            signals.append(f"High operating margin: {om_pct:.1f}%")
            score_components.append(85)
        elif om_pct > 15:
            signals.append(f"Healthy operating margin: {om_pct:.1f}%")
            score_components.append(65)
        else:
            signals.append(f"Low operating margin: {om_pct:.1f}%")
            score_components.append(35)

    score = sum(score_components) / len(score_components) if score_components else None
    return {"score": round(score, 1) if score else None, "signals": signals}


def _analyze_growth(f: dict) -> dict:
    signals = []
    score_components = []

    eg = f.get("earnings_growth")
    if eg is not None:
        eg_pct = eg * 100
        if eg_pct > 25:
            signals.append(f"Strong earnings growth: {eg_pct:.1f}%")
            score_components.append(90)
        elif eg_pct > 10:
            signals.append(f"Moderate earnings growth: {eg_pct:.1f}%")
            score_components.append(65)
        elif eg_pct > 0:
            signals.append(f"Slow earnings growth: {eg_pct:.1f}%")
            score_components.append(45)
        else:
            signals.append(f"Earnings declining: {eg_pct:.1f}%")
            score_components.append(20)

    rg = f.get("revenue_growth")
    if rg is not None:
        rg_pct = rg * 100
        if rg_pct > 20:
            signals.append(f"Strong revenue growth: {rg_pct:.1f}%")
            score_components.append(85)
        elif rg_pct > 10:
            signals.append(f"Good revenue growth: {rg_pct:.1f}%")
            score_components.append(65)
        elif rg_pct > 0:
            signals.append(f"Slow revenue growth: {rg_pct:.1f}%")
            score_components.append(45)
        else:
            signals.append(f"Revenue declining: {rg_pct:.1f}%")
            score_components.append(20)

    score = sum(score_components) / len(score_components) if score_components else None
    return {"score": round(score, 1) if score else None, "signals": signals}


def _analyze_financial_health(f: dict, bs: dict) -> dict:
    signals = []
    score_components = []

    dte = f.get("debt_to_equity")
    if dte is not None:
        if dte < 30:
            signals.append(f"Very low debt (D/E: {dte:.1f})")
            score_components.append(90)
        elif dte < 100:
            signals.append(f"Manageable debt (D/E: {dte:.1f})")
            score_components.append(65)
        elif dte < 200:
            signals.append(f"High debt (D/E: {dte:.1f})")
            score_components.append(35)
        else:
            signals.append(f"Very high debt (D/E: {dte:.1f})")
            score_components.append(15)

    cr = f.get("current_ratio")
    if cr is not None:
        if cr > 2:
            signals.append(f"Strong liquidity (Current ratio: {cr:.2f})")
            score_components.append(80)
        elif cr > 1:
            signals.append(f"Adequate liquidity (Current ratio: {cr:.2f})")
            score_components.append(60)
        else:
            signals.append(f"Liquidity concern (Current ratio: {cr:.2f})")
            score_components.append(25)

    fcf = f.get("free_cash_flow")
    if fcf is not None:
        if fcf > 0:
            signals.append("Positive free cash flow")
            score_components.append(75)
        else:
            signals.append("Negative free cash flow")
            score_components.append(25)

    if bs.get("available"):
        cash = bs.get("cash")
        debt = bs.get("total_debt")
        if cash and debt:
            if cash > debt:
                signals.append("Cash exceeds total debt — net cash position")
                score_components.append(90)
            else:
                ratio = debt / cash if cash > 0 else float('inf')
                signals.append(f"Debt-to-cash ratio: {ratio:.1f}x")
                score_components.append(50 if ratio < 3 else 25)

    score = sum(score_components) / len(score_components) if score_components else None
    return {"score": round(score, 1) if score else None, "signals": signals}


def _analyze_analyst_sentiment(f: dict) -> dict:
    signals = []
    score_components = []

    rec = f.get("recommendation")
    if rec:
        rec_scores = {
            "strongBuy": 90, "buy": 75, "hold": 50,
            "sell": 25, "strongSell": 10,
            "strong_buy": 90, "underperform": 30, "outperform": 70,
        }
        score_val = rec_scores.get(rec, 50)
        signals.append(f"Analyst consensus: {rec}")
        score_components.append(score_val)

    target = f.get("target_mean_price")
    current_price_approx = f.get("50_day_avg")
    if target and current_price_approx:
        upside = ((target - current_price_approx) / current_price_approx) * 100
        signals.append(f"Analyst target implies {upside:.1f}% {'upside' if upside > 0 else 'downside'}")
        if upside > 20:
            score_components.append(85)
        elif upside > 10:
            score_components.append(70)
        elif upside > 0:
            score_components.append(55)
        else:
            score_components.append(30)

    n_analysts = f.get("number_of_analysts")
    if n_analysts:
        signals.append(f"Covered by {n_analysts} analysts")

    score = sum(score_components) / len(score_components) if score_components else None
    return {"score": round(score, 1) if score else None, "signals": signals}
