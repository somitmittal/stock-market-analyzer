"""
Signal scoring engine.
Combines technical and fundamental analysis into entry/exit signals
with probability scores.
"""
import pandas as pd
import numpy as np
from typing import Optional


def generate_signals(
    df: pd.DataFrame,
    technical: dict,
    fundamental_analysis: dict,
    earnings: list[dict],
    news: list[dict],
) -> dict:
    """
    Generate entry/exit signals with probability scores.
    Returns current recommendation, historical signals, and reasoning.
    """
    tech_score = _score_technical(technical)
    fund_score = fundamental_analysis.get("overall_score", 50)
    earnings_modifier = _score_earnings_proximity(earnings)
    news_modifier = _score_news_sentiment(news)

    # Weighted composite: technicals 50%, fundamentals 30%, earnings 10%, news 10%
    composite = (
        tech_score["score"] * 0.50
        + fund_score * 0.30
        + earnings_modifier * 0.10
        + news_modifier * 0.10
    )

    entry_probability = min(95, max(5, composite))
    exit_probability = min(95, max(5, 100 - composite))

    current_price = float(df["Close"].iloc[-1])
    atr = technical.get("atr", {}).get("value") or current_price * 0.02
    sr = technical.get("support_resistance", {})

    entry_price = _calculate_entry_price(current_price, technical, sr, atr)
    exit_price = _calculate_exit_price(current_price, technical, sr, atr)
    stop_loss = _calculate_stop_loss(entry_price, technical, sr, atr)

    risk_reward = abs(exit_price - entry_price) / abs(entry_price - stop_loss) if abs(entry_price - stop_loss) > 0 else 0

    action = _determine_action(entry_probability, tech_score, fundamental_analysis)

    historical_signals = _generate_historical_signals(df, technical)

    return {
        "action": action,
        "confidence": round(entry_probability, 1),
        "entry": {
            "price": round(entry_price, 2),
            "probability": round(entry_probability, 1),
            "reasoning": tech_score["entry_reasons"],
        },
        "exit": {
            "target_price": round(exit_price, 2),
            "probability": round(exit_probability, 1),
            "reasoning": tech_score["exit_reasons"],
        },
        "stop_loss": round(stop_loss, 2),
        "risk_reward_ratio": round(risk_reward, 2),
        "score_breakdown": {
            "technical": round(tech_score["score"], 1),
            "fundamental": round(fund_score, 1),
            "earnings_proximity": round(earnings_modifier, 1),
            "news_sentiment": round(news_modifier, 1),
            "composite": round(composite, 1),
        },
        "technical_signals": tech_score["signals"],
        "historical_signals": historical_signals,
    }


def _score_technical(t: dict) -> dict:
    score = 50.0
    signals = []
    entry_reasons = []
    exit_reasons = []

    rsi = t.get("rsi", {})
    rsi_val = rsi.get("value")
    if rsi_val is not None:
        if rsi_val < 30:
            score += 15
            signals.append({"indicator": "RSI", "signal": "oversold", "impact": "+15"})
            entry_reasons.append(f"RSI at {rsi_val} — oversold, potential bounce")
        elif rsi_val < 40:
            score += 8
            signals.append({"indicator": "RSI", "signal": "approaching_oversold", "impact": "+8"})
            entry_reasons.append(f"RSI at {rsi_val} — approaching oversold")
        elif rsi_val > 70:
            score -= 15
            signals.append({"indicator": "RSI", "signal": "overbought", "impact": "-15"})
            exit_reasons.append(f"RSI at {rsi_val} — overbought, consider booking profits")
        elif rsi_val > 60:
            score -= 5
            signals.append({"indicator": "RSI", "signal": "approaching_overbought", "impact": "-5"})

    if rsi.get("divergence") == "bullish_divergence":
        score += 10
        signals.append({"indicator": "RSI", "signal": "bullish_divergence", "impact": "+10"})
        entry_reasons.append("Bullish RSI divergence detected")
    elif rsi.get("divergence") == "bearish_divergence":
        score -= 10
        signals.append({"indicator": "RSI", "signal": "bearish_divergence", "impact": "-10"})
        exit_reasons.append("Bearish RSI divergence detected")

    macd = t.get("macd", {})
    if macd.get("crossover") == "bullish":
        score += 12
        signals.append({"indicator": "MACD", "signal": "bullish_crossover", "impact": "+12"})
        entry_reasons.append("MACD bullish crossover — momentum shifting up")
    elif macd.get("crossover") == "bearish":
        score -= 12
        signals.append({"indicator": "MACD", "signal": "bearish_crossover", "impact": "-12"})
        exit_reasons.append("MACD bearish crossover — momentum shifting down")
    elif macd.get("trend") == "bullish":
        score += 5
        signals.append({"indicator": "MACD", "signal": "bullish_trend", "impact": "+5"})
    elif macd.get("trend") == "bearish":
        score -= 5
        signals.append({"indicator": "MACD", "signal": "bearish_trend", "impact": "-5"})

    bb = t.get("bollinger", {})
    bb_signal = bb.get("signal")
    if bb_signal == "below_lower_band":
        score += 12
        signals.append({"indicator": "Bollinger", "signal": "below_lower_band", "impact": "+12"})
        entry_reasons.append("Price below lower Bollinger Band — potential reversal zone")
    elif bb_signal == "near_lower_band":
        score += 6
        signals.append({"indicator": "Bollinger", "signal": "near_lower_band", "impact": "+6"})
    elif bb_signal == "above_upper_band":
        score -= 12
        signals.append({"indicator": "Bollinger", "signal": "above_upper_band", "impact": "-12"})
        exit_reasons.append("Price above upper Bollinger Band — extended, may revert")
    elif bb_signal == "near_upper_band":
        score -= 6
        signals.append({"indicator": "Bollinger", "signal": "near_upper_band", "impact": "-6"})

    ma = t.get("moving_averages", {})
    ma_overall = ma.get("overall", "neutral")
    if ma_overall == "strong_bullish":
        score += 10
        signals.append({"indicator": "Moving Averages", "signal": "all_bullish", "impact": "+10"})
        entry_reasons.append("Price above all key moving averages — strong uptrend")
    elif ma_overall == "bullish":
        score += 5
        signals.append({"indicator": "Moving Averages", "signal": "mostly_bullish", "impact": "+5"})
    elif ma_overall == "bearish":
        score -= 8
        signals.append({"indicator": "Moving Averages", "signal": "mostly_bearish", "impact": "-8"})
        exit_reasons.append("Price below key moving averages — downtrend")

    cross = ma.get("cross", "none")
    if cross == "golden_cross":
        score += 10
        signals.append({"indicator": "MA Cross", "signal": "golden_cross", "impact": "+10"})
        entry_reasons.append("Golden cross (50 SMA > 200 SMA) — major bullish signal")
    elif cross == "death_cross":
        score -= 10
        signals.append({"indicator": "MA Cross", "signal": "death_cross", "impact": "-10"})
        exit_reasons.append("Death cross (50 SMA < 200 SMA) — major bearish signal")

    stoch = t.get("stochastic", {})
    if stoch.get("signal") == "oversold":
        score += 8
        signals.append({"indicator": "Stochastic", "signal": "oversold", "impact": "+8"})
        entry_reasons.append("Stochastic oversold — buying opportunity")
    elif stoch.get("signal") == "overbought":
        score -= 8
        signals.append({"indicator": "Stochastic", "signal": "overbought", "impact": "-8"})
        exit_reasons.append("Stochastic overbought — profit booking zone")

    adx = t.get("adx", {})
    if adx.get("trend_strength") in ("strong", "very_strong"):
        if adx.get("direction") == "bullish":
            score += 8
            signals.append({"indicator": "ADX", "signal": "strong_bullish_trend", "impact": "+8"})
            entry_reasons.append(f"ADX {adx.get('adx')} with bullish DI — strong uptrend")
        else:
            score -= 8
            signals.append({"indicator": "ADX", "signal": "strong_bearish_trend", "impact": "-8"})
            exit_reasons.append(f"ADX {adx.get('adx')} with bearish DI — strong downtrend")

    vol = t.get("volume_analysis", {})
    if vol.get("volume_signal") == "high" and vol.get("obv_trend") == "rising":
        score += 5
        signals.append({"indicator": "Volume", "signal": "high_bullish_volume", "impact": "+5"})
        entry_reasons.append("High volume with rising OBV — institutional buying")
    elif vol.get("volume_signal") == "high" and vol.get("obv_trend") == "falling":
        score -= 5
        signals.append({"indicator": "Volume", "signal": "high_bearish_volume", "impact": "-5"})
        exit_reasons.append("High volume with falling OBV — distribution")

    patterns = t.get("candlestick_patterns", [])
    for p in patterns:
        if "bullish" in p.get("signal", ""):
            score += 6
            signals.append({"indicator": "Candlestick", "signal": p["pattern"], "impact": "+6"})
            entry_reasons.append(f"{p['pattern']} pattern detected — bullish reversal")
        elif "bearish" in p.get("signal", ""):
            score -= 6
            signals.append({"indicator": "Candlestick", "signal": p["pattern"], "impact": "-6"})
            exit_reasons.append(f"{p['pattern']} pattern detected — bearish reversal")

    score = max(5, min(95, score))

    if not entry_reasons:
        entry_reasons.append("No strong entry signals detected currently")
    if not exit_reasons:
        exit_reasons.append("No strong exit signals detected currently")

    return {
        "score": score,
        "signals": signals,
        "entry_reasons": entry_reasons,
        "exit_reasons": exit_reasons,
    }


def _score_earnings_proximity(earnings: list[dict]) -> float:
    """Modifier based on upcoming earnings — adds uncertainty."""
    if not earnings:
        return 50

    from datetime import datetime
    for e in earnings:
        try:
            date_str = e.get("date", "")
            if "Timestamp" in date_str:
                return 50
            earn_date = pd.Timestamp(date_str)
            days_away = (earn_date - pd.Timestamp.now()).days
            if 0 < days_away <= 7:
                return 40  # High uncertainty near earnings
            elif 0 < days_away <= 30:
                return 55
            if e.get("surprise_pct") is not None:
                surprise = e["surprise_pct"]
                if surprise > 5:
                    return 70
                elif surprise < -5:
                    return 30
        except Exception:
            continue
    return 50


def _score_news_sentiment(news: list[dict]) -> float:
    """Basic keyword-based news sentiment scoring."""
    if not news:
        return 50

    positive_keywords = [
        "upgrade", "beat", "growth", "profit", "surge", "rally", "strong",
        "outperform", "bullish", "record", "raises", "expansion", "exceeds",
        "positive", "buy", "dividend", "breakout",
    ]
    negative_keywords = [
        "downgrade", "miss", "loss", "decline", "fall", "crash", "weak",
        "underperform", "bearish", "concern", "warning", "cuts", "layoff",
        "negative", "sell", "debt", "fraud", "probe", "investigation",
    ]

    pos_count = 0
    neg_count = 0
    for article in news:
        title = (article.get("title", "") or "").lower()
        for kw in positive_keywords:
            if kw in title:
                pos_count += 1
        for kw in negative_keywords:
            if kw in title:
                neg_count += 1

    if pos_count == 0 and neg_count == 0:
        return 50

    sentiment = (pos_count - neg_count) / (pos_count + neg_count)
    return 50 + sentiment * 30


def _calculate_entry_price(price: float, technical: dict, sr: dict, atr: float) -> float:
    support1 = sr.get("support_1", price - atr)
    bb_lower = technical.get("bollinger", {}).get("lower", price - atr)

    if price < support1:
        return round(price, 2)

    ideal_entry = max(support1, bb_lower) if bb_lower else support1
    if ideal_entry > price:
        ideal_entry = price - atr * 0.5
    return round(ideal_entry, 2)


def _calculate_exit_price(price: float, technical: dict, sr: dict, atr: float) -> float:
    resistance1 = sr.get("resistance_1", price + atr)
    bb_upper = technical.get("bollinger", {}).get("upper", price + atr)

    ideal_exit = min(resistance1, bb_upper) if bb_upper else resistance1
    if ideal_exit < price:
        ideal_exit = price + atr * 1.5
    return round(ideal_exit, 2)


def _calculate_stop_loss(entry_price: float, technical: dict, sr: dict, atr: float) -> float:
    support2 = sr.get("support_2", entry_price - atr * 2)
    atr_stop = entry_price - atr * 1.5
    return round(max(support2, atr_stop), 2)


def _determine_action(probability: float, tech_score: dict, fund_analysis: dict) -> str:
    """
    STRONG BUY requires ALL of:
      1. Composite score >= 80
      2. Technical score >= 75 (multiple indicators must agree)
      3. Fundamentals not negative (>= 45)
      4. At least 4 bullish technical signals firing
    This ensures STRONG BUY only appears at high-confluence points
    where the probability of making maximum returns is highest.
    """
    fund_score = fund_analysis.get("overall_score", 50)
    fund_signal = fund_analysis.get("overall_signal", "hold")
    tech_val = tech_score.get("score", 50)
    bullish_signal_count = sum(
        1 for s in tech_score.get("signals", [])
        if s.get("impact", "").startswith("+")
    )

    # STRONG BUY: very high bar — multiple confirmations required
    if (probability >= 80
            and tech_val >= 75
            and fund_score >= 45
            and bullish_signal_count >= 4):
        return "STRONG BUY"

    # BUY: solid confluence
    if probability >= 68 and tech_val >= 60:
        if fund_signal in ("strong_buy", "buy") or fund_score >= 55:
            return "BUY"
        return "LEAN BUY"

    if probability >= 58:
        return "LEAN BUY" if probability >= 55 and tech_val >= 55 else "HOLD"

    if probability >= 45:
        return "HOLD"

    # Mirror logic for sell side
    bearish_signal_count = sum(
        1 for s in tech_score.get("signals", [])
        if s.get("impact", "").startswith("-")
    )

    if (probability <= 20
            and tech_val <= 25
            and bearish_signal_count >= 4):
        return "STRONG SELL"

    if probability <= 32:
        if fund_signal in ("sell", "strong_sell"):
            return "SELL"
        return "LEAN SELL"

    return "LEAN SELL"


def _detect_swing_points(high: pd.Series, low: pd.Series, lookback: int = 5):
    """
    Detect swing highs and swing lows using a rolling window.
    A swing high is a bar whose high is the highest in ±lookback bars.
    """
    n = len(high)
    swing_highs = pd.Series(False, index=high.index)
    swing_lows = pd.Series(False, index=low.index)
    for i in range(lookback, n - lookback):
        window_high = high.iloc[i - lookback : i + lookback + 1]
        window_low = low.iloc[i - lookback : i + lookback + 1]
        if float(high.iloc[i]) == float(window_high.max()):
            swing_highs.iloc[i] = True
        if float(low.iloc[i]) == float(window_low.min()):
            swing_lows.iloc[i] = True
    return swing_highs, swing_lows


# ═══════════════════════════════════════════════════════════════════
# LAYER 1 — TREND & CONTEXT
# ═══════════════════════════════════════════════════════════════════

def _classify_trend(price: float, ema50: pd.Series, ema200: pd.Series,
                    swing_highs: pd.Series, swing_lows: pd.Series,
                    high: pd.Series, low: pd.Series, close: pd.Series,
                    i: int) -> dict:
    """
    Classify market regime at bar i.

    Returns dict with:
      trend: "strong_uptrend" | "uptrend" | "neutral" | "downtrend" | "strong_downtrend"
      factors: list of reasons
      bullish_factors: int (count of trend factors supporting a long)
      bearish_factors: int (count of trend factors supporting a short)
    """
    bullish = 0
    bearish = 0
    reasons = []

    e50 = float(ema50.iloc[i]) if not pd.isna(ema50.iloc[i]) else None
    e200 = float(ema200.iloc[i]) if not pd.isna(ema200.iloc[i]) else None

    # Price vs 200 EMA (the primary trend filter per the blueprint)
    if e200 is not None:
        if price > e200:
            bullish += 1
            reasons.append("Price > 200 EMA")
        else:
            bearish += 1
            reasons.append("Price < 200 EMA")

    # Price vs 50 EMA
    if e50 is not None:
        if price > e50:
            bullish += 1
            reasons.append("Price > 50 EMA")
        else:
            bearish += 1
            reasons.append("Price < 50 EMA")

    # 50/200 EMA alignment (golden/death cross)
    if e50 is not None and e200 is not None:
        if e50 > e200:
            bullish += 1
            reasons.append("Golden cross")
        else:
            bearish += 1
            reasons.append("Death cross")

    # Swing structure: HH/HL vs LH/LL (look at last 3 pairs in 120-bar window)
    recent_sh = []
    recent_sl = []
    lookback_window = min(i, 120)
    for j in range(i - lookback_window, i + 1):
        if j < 0:
            continue
        if swing_highs.iloc[j]:
            recent_sh.append(float(high.iloc[j]))
        if swing_lows.iloc[j]:
            recent_sl.append(float(low.iloc[j]))

    hh, lh, hl, ll = 0, 0, 0, 0
    for k in range(1, min(len(recent_sh), 4)):
        if recent_sh[-k] > recent_sh[-(k+1)]:
            hh += 1
        else:
            lh += 1
    for k in range(1, min(len(recent_sl), 4)):
        if recent_sl[-k] > recent_sl[-(k+1)]:
            hl += 1
        else:
            ll += 1

    if hh >= 2 and hl >= 2:
        bullish += 1
        reasons.append("HH + HL")
    elif lh >= 2 and ll >= 2:
        bearish += 1
        reasons.append("LH + LL")

    # Drawdown from 120-day high (catches corrections before death cross)
    lookback_120 = min(i + 1, 120)
    recent_high = float(high.iloc[i - lookback_120 + 1 : i + 1].max())
    if recent_high > 0:
        drawdown_pct = (recent_high - price) / recent_high * 100
        if drawdown_pct >= 15:
            bearish += 2
            reasons.append(f"Down {drawdown_pct:.0f}%")

    net = bullish - bearish
    if net >= 4:
        trend = "strong_uptrend"
    elif net >= 2:
        trend = "uptrend"
    elif net <= -4:
        trend = "strong_downtrend"
    elif net <= -2:
        trend = "downtrend"
    else:
        trend = "neutral"

    return {
        "trend": trend,
        "factors": reasons,
        "bullish_factors": bullish,
        "bearish_factors": bearish,
    }


# ═══════════════════════════════════════════════════════════════════
# LAYER 2 — PRICE ACTION & LEVELS
# ═══════════════════════════════════════════════════════════════════

def _find_nearest_support_resistance(high: pd.Series, low: pd.Series,
                                      swing_highs: pd.Series, swing_lows: pd.Series,
                                      i: int, price: float) -> tuple[float | None, float | None]:
    """Find the nearest swing-based support below and resistance above."""
    support = None
    resistance = None
    for j in range(i - 1, max(i - 150, -1), -1):
        if j < 0:
            break
        if swing_lows.iloc[j]:
            lvl = float(low.iloc[j])
            if lvl < price and (support is None or lvl > support):
                support = lvl
        if swing_highs.iloc[j]:
            lvl = float(high.iloc[j])
            if lvl > price and (resistance is None or lvl < resistance):
                resistance = lvl
        if support is not None and resistance is not None:
            break
    return support, resistance


def _is_near_key_level(price: float, support: float | None,
                       resistance: float | None, atr_val: float) -> tuple[bool, bool, str | None]:
    """Check if price is within 1.5 ATR of a key support or resistance zone."""
    near_support = support is not None and 0 < (price - support) < atr_val * 1.5
    near_resistance = resistance is not None and 0 < (resistance - price) < atr_val * 1.5
    level_name = None
    if near_support:
        level_name = f"Near support ₹{support:.0f}"
    elif near_resistance:
        level_name = f"Near resistance ₹{resistance:.0f}"
    return near_support, near_resistance, level_name


def _detect_candlestick_patterns(open_: pd.Series, high: pd.Series,
                                  low: pd.Series, close: pd.Series,
                                  i: int) -> list[dict]:
    """
    Detect key reversal candlestick patterns at bar i.
    Returns list of {"name": str, "bias": "bullish"|"bearish"}.
    """
    patterns = []
    if i < 2:
        return patterns

    o = float(open_.iloc[i])
    h = float(high.iloc[i])
    l = float(low.iloc[i])
    c = float(close.iloc[i])
    po = float(open_.iloc[i-1])
    ph = float(high.iloc[i-1])
    pl = float(low.iloc[i-1])
    pc = float(close.iloc[i-1])

    body = abs(c - o)
    range_ = h - l
    prev_body = abs(pc - po)

    if range_ == 0 or (h - l) < 1e-8:
        return patterns

    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l

    # Bullish Engulfing
    if pc < po and c > o:
        if o <= pc and c >= po and body > prev_body * 0.8:
            patterns.append({"name": "Bullish Engulfing", "bias": "bullish"})

    # Bearish Engulfing
    if pc > po and c < o:
        if o >= pc and c <= po and body > prev_body * 0.8:
            patterns.append({"name": "Bearish Engulfing", "bias": "bearish"})

    # Hammer (bullish — small body at top, long lower wick)
    if body > 0 and lower_shadow >= 2 * body and upper_shadow <= body * 0.5:
        patterns.append({"name": "Hammer", "bias": "bullish"})

    # Shooting Star (bearish — small body at bottom, long upper wick)
    if body > 0 and upper_shadow >= 2 * body and lower_shadow <= body * 0.5:
        patterns.append({"name": "Shooting Star", "bias": "bearish"})

    # Morning Star (3-bar bullish reversal)
    if i >= 2:
        ppo = float(open_.iloc[i-2])
        ppc = float(close.iloc[i-2])
        if ppc < ppo:  # bar i-2 bearish
            mid_body = prev_body
            mid_range = ph - pl
            if mid_range > 0 and mid_body / mid_range < 0.3:
                if c > o and c > (ppo + ppc) / 2:
                    patterns.append({"name": "Morning Star", "bias": "bullish"})

    # Evening Star (3-bar bearish reversal)
    if i >= 2:
        ppo = float(open_.iloc[i-2])
        ppc = float(close.iloc[i-2])
        if ppc > ppo:  # bar i-2 bullish
            mid_body = prev_body
            mid_range = ph - pl
            if mid_range > 0 and mid_body / mid_range < 0.3:
                if c < o and c < (ppo + ppc) / 2:
                    patterns.append({"name": "Evening Star", "bias": "bearish"})

    return patterns


# ═══════════════════════════════════════════════════════════════════
# LAYER 3 — MOMENTUM & VOLUME
# ═══════════════════════════════════════════════════════════════════

def _detect_rsi_divergence(close: pd.Series, rsi: pd.Series,
                           swing_lows: pd.Series, swing_highs: pd.Series,
                           low: pd.Series, high: pd.Series,
                           i: int, lookback: int = 60) -> str | None:
    """
    Detect RSI divergence at bar i.
    Bullish: price makes lower low, RSI makes higher low.
    Bearish: price makes higher high, RSI makes lower high.
    """
    # Bullish divergence: find last 2 swing lows
    sl_indices = []
    for j in range(i, max(i - lookback, -1), -1):
        if swing_lows.iloc[j]:
            sl_indices.append(j)
            if len(sl_indices) >= 2:
                break

    if len(sl_indices) >= 2:
        sl1, sl2 = sl_indices[0], sl_indices[1]
        p1, p2 = float(low.iloc[sl1]), float(low.iloc[sl2])
        r1 = float(rsi.iloc[sl1]) if not pd.isna(rsi.iloc[sl1]) else None
        r2 = float(rsi.iloc[sl2]) if not pd.isna(rsi.iloc[sl2]) else None
        if r1 is not None and r2 is not None:
            if p1 < p2 and r1 > r2:
                return "bullish"

    # Bearish divergence: find last 2 swing highs
    sh_indices = []
    for j in range(i, max(i - lookback, -1), -1):
        if swing_highs.iloc[j]:
            sh_indices.append(j)
            if len(sh_indices) >= 2:
                break

    if len(sh_indices) >= 2:
        sh1, sh2 = sh_indices[0], sh_indices[1]
        p1, p2 = float(high.iloc[sh1]), float(high.iloc[sh2])
        r1 = float(rsi.iloc[sh1]) if not pd.isna(rsi.iloc[sh1]) else None
        r2 = float(rsi.iloc[sh2]) if not pd.isna(rsi.iloc[sh2]) else None
        if r1 is not None and r2 is not None:
            if p1 > p2 and r1 < r2:
                return "bearish"

    return None


# ═══════════════════════════════════════════════════════════════════
# MAIN SIGNAL ENGINE — 3-FACTOR CONFLUENCE
# ═══════════════════════════════════════════════════════════════════

def _generate_historical_signals(df: pd.DataFrame, technical: dict) -> list[dict]:
    """
    Institutional-grade signal engine using 3-category confluence.

    A signal requires confirming factors from ALL THREE categories:
      1. TREND & CONTEXT  — Price vs 200 EMA, market structure, SMA alignment
      2. PRICE ACTION      — Near key S/R level, candlestick reversal pattern,
                             or Bollinger Band reclaim/rejection
      3. MOMENTUM & VOLUME — RSI reversal/divergence, MACD crossover,
                             Stochastic cross, volume confirmation

    Rules:
      - Only LONG in uptrend/neutral, only SHORT in downtrend/neutral
      - Every entry has SL (1.5 ATR below swing low), TP1 (nearest resistance),
        TP2 (1:3 RRR or next major level)
      - Minimum RRR 1:2.0 or trade is rejected
      - Alternating buy/sell pairs with minimum 25-day spacing
      - Forced exit if stop-loss breached or price drops >10% from entry
    """
    import ta as ta_lib

    close = df["Close"]
    open_ = df["Open"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    n = len(df)
    if n < 200:
        return []

    # ── Compute all indicators ──
    rsi = ta_lib.momentum.RSIIndicator(close, window=14).rsi()
    macd_ind = ta_lib.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_line = macd_ind.macd()
    macd_signal_line = macd_ind.macd_signal()
    bb = ta_lib.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_lower = bb.bollinger_lband()
    bb_upper = bb.bollinger_hband()
    stoch = ta_lib.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
    stoch_k = stoch.stoch()
    stoch_d = stoch.stoch_signal()
    atr_ind = ta_lib.volatility.AverageTrueRange(high, low, close, window=14)
    atr = atr_ind.average_true_range()

    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    vol_ma20 = volume.rolling(20).mean()

    swing_highs, swing_lows = _detect_swing_points(high, low, lookback=5)

    raw_signals = []

    for i in range(200, n):
        price = float(close.iloc[i])
        date = str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i])
        cur_atr = float(atr.iloc[i]) if not pd.isna(atr.iloc[i]) else price * 0.02

        # ════════════════════════════════════════════════════════════
        # CATEGORY 1: TREND & CONTEXT
        # ════════════════════════════════════════════════════════════
        trend_info = _classify_trend(
            price, ema50, ema200, swing_highs, swing_lows,
            high, low, close, i
        )
        trend = trend_info["trend"]
        is_bullish = trend in ("strong_uptrend", "uptrend")
        is_bearish = trend in ("strong_downtrend", "downtrend")

        trend_buy_score = trend_info["bullish_factors"]
        trend_sell_score = trend_info["bearish_factors"]
        has_trend_buy = trend_buy_score >= 2 and not is_bearish
        has_trend_sell = trend_sell_score >= 2 and not is_bullish

        # ════════════════════════════════════════════════════════════
        # CATEGORY 2: PRICE ACTION & LEVELS
        # ════════════════════════════════════════════════════════════
        support, resistance = _find_nearest_support_resistance(
            high, low, swing_highs, swing_lows, i, price
        )
        near_support, near_resistance, level_name = _is_near_key_level(
            price, support, resistance, cur_atr
        )

        candle_patterns = _detect_candlestick_patterns(open_, high, low, close, i)
        bullish_candles = [p for p in candle_patterns if p["bias"] == "bullish"]
        bearish_candles = [p for p in candle_patterns if p["bias"] == "bearish"]

        bb_reclaim = False
        bb_rejection = False
        if not pd.isna(bb_lower.iloc[i]) and not pd.isna(bb_lower.iloc[i-1]):
            if float(close.iloc[i-1]) < float(bb_lower.iloc[i-1]) and price >= float(bb_lower.iloc[i]):
                bb_reclaim = True
        if not pd.isna(bb_upper.iloc[i]) and not pd.isna(bb_upper.iloc[i-1]):
            if float(close.iloc[i-1]) > float(bb_upper.iloc[i-1]) and price <= float(bb_upper.iloc[i]):
                bb_rejection = True

        pa_buy_score = int(near_support) + int(len(bullish_candles) > 0) + int(bb_reclaim)
        pa_sell_score = int(near_resistance) + int(len(bearish_candles) > 0) + int(bb_rejection)
        has_pa_buy = pa_buy_score >= 1
        has_pa_sell = pa_sell_score >= 1

        # ════════════════════════════════════════════════════════════
        # CATEGORY 3: MOMENTUM & VOLUME
        # ════════════════════════════════════════════════════════════
        mom_buy_score = 0
        mom_sell_score = 0
        mom_buy_reasons = []
        mom_sell_reasons = []

        # RSI reversal from extreme
        if not pd.isna(rsi.iloc[i]) and not pd.isna(rsi.iloc[i-1]):
            r_now, r_prev = float(rsi.iloc[i]), float(rsi.iloc[i-1])
            if r_prev < 30 and r_now >= 30:
                mom_buy_score += 1
                mom_buy_reasons.append("RSI ↑30")
            elif r_prev < 40 and r_now >= 40 and r_prev > 25:
                mom_buy_score += 1
                mom_buy_reasons.append("RSI recovering")
            if r_prev > 70 and r_now <= 70:
                mom_sell_score += 1
                mom_sell_reasons.append("RSI ↓70")
            elif r_prev > 60 and r_now <= 60 and r_prev < 75:
                mom_sell_score += 1
                mom_sell_reasons.append("RSI weakening")

        # RSI divergence
        div = _detect_rsi_divergence(close, rsi, swing_lows, swing_highs, low, high, i)
        if div == "bullish":
            mom_buy_score += 1
            mom_buy_reasons.append("RSI bull divergence")
        elif div == "bearish":
            mom_sell_score += 1
            mom_sell_reasons.append("RSI bear divergence")

        # MACD line / signal line crossover
        if (not pd.isna(macd_line.iloc[i]) and not pd.isna(macd_signal_line.iloc[i])
                and not pd.isna(macd_line.iloc[i-1]) and not pd.isna(macd_signal_line.iloc[i-1])):
            ml, ms = float(macd_line.iloc[i]), float(macd_signal_line.iloc[i])
            ml_p, ms_p = float(macd_line.iloc[i-1]), float(macd_signal_line.iloc[i-1])
            if ml_p <= ms_p and ml > ms:
                mom_buy_score += 1
                mom_buy_reasons.append("MACD cross ↑")
            elif ml_p >= ms_p and ml < ms:
                mom_sell_score += 1
                mom_sell_reasons.append("MACD cross ↓")

        # Stochastic %K/%D cross in extreme zone
        if (not pd.isna(stoch_k.iloc[i]) and not pd.isna(stoch_d.iloc[i])
                and not pd.isna(stoch_k.iloc[i-1]) and not pd.isna(stoch_d.iloc[i-1])):
            k_n, d_n = float(stoch_k.iloc[i]), float(stoch_d.iloc[i])
            k_p, d_p = float(stoch_k.iloc[i-1]), float(stoch_d.iloc[i-1])
            if k_p <= d_p and k_n > d_n and k_n < 25:
                mom_buy_score += 1
                mom_buy_reasons.append("Stoch cross ↑")
            elif k_p >= d_p and k_n < d_n and k_n > 75:
                mom_sell_score += 1
                mom_sell_reasons.append("Stoch cross ↓")

        # Volume confirmation (expanding volume on signal candle)
        vol_confirmed = False
        if not pd.isna(vol_ma20.iloc[i]):
            avg_v = float(vol_ma20.iloc[i])
            cur_v = float(volume.iloc[i])
            if avg_v > 0 and cur_v > avg_v * 1.3:
                vol_confirmed = True
                mom_buy_score += 1 if mom_buy_score > 0 else 0
                mom_sell_score += 1 if mom_sell_score > 0 else 0

        has_mom_buy = mom_buy_score >= 1
        has_mom_sell = mom_sell_score >= 1

        # ════════════════════════════════════════════════════════════
        # CONFLUENCE GATE: need at least 1 factor from EACH category
        # ════════════════════════════════════════════════════════════
        buy_confluence = has_trend_buy and has_pa_buy and has_mom_buy
        sell_confluence = has_trend_sell and has_pa_sell and has_mom_sell

        if not buy_confluence and not sell_confluence:
            continue

        total_buy = trend_buy_score + pa_buy_score + mom_buy_score
        total_sell = trend_sell_score + pa_sell_score + mom_sell_score

        # ════════════════════════════════════════════════════════════
        # EXECUTION: SL, TP1, TP2, RRR check
        # ════════════════════════════════════════════════════════════
        if buy_confluence and total_buy > total_sell:
            # SL: 1.5 ATR below nearest swing low, floor at 2.5 ATR below entry
            swing_stop = (support - cur_atr * 1.5) if support is not None else None
            atr_stop = price - cur_atr * 2.5
            if swing_stop is not None and swing_stop < price:
                stop = min(swing_stop, atr_stop)
            else:
                stop = atr_stop

            tp1 = resistance if resistance is not None else price + cur_atr * 4
            risk = abs(price - stop)
            tp2 = price + risk * 3

            if risk <= 0:
                continue
            rr1 = abs(tp1 - price) / risk
            rr2 = abs(tp2 - price) / risk

            if rr1 < 2.0 and rr2 < 2.0:
                continue

            best_rr = max(rr1, rr2)

            # Build reason string
            reasons = []
            if bullish_candles:
                reasons.append(bullish_candles[0]["name"])
            if near_support and level_name:
                reasons.append(level_name)
            elif bb_reclaim:
                reasons.append("BB reclaim")
            reasons.extend(mom_buy_reasons[:2])
            if vol_confirmed:
                reasons.append("Vol ✓")

            confidence = _calculate_signal_confidence(
                total_buy, trend, vol_confirmed, best_rr, "entry"
            )

            raw_signals.append({
                "idx": i, "date": date, "price": round(price, 2),
                "type": "entry",
                "reason": " · ".join(reasons[:4]),
                "confidence": confidence,
                "total_factors": total_buy,
                "trend": trend,
                "stop": round(stop, 2),
                "tp1": round(tp1, 2),
                "tp2": round(tp2, 2),
                "target": round(tp1, 2),
                "rr": round(best_rr, 1),
            })

        elif sell_confluence and total_sell > total_buy:
            swing_stop = (resistance + cur_atr * 1.5) if resistance is not None else None
            atr_stop = price + cur_atr * 2.5
            if swing_stop is not None and swing_stop > price:
                stop = max(swing_stop, atr_stop)
            else:
                stop = atr_stop

            tp1 = support if support is not None else price - cur_atr * 4
            risk = abs(stop - price)
            tp2 = price - risk * 3

            if risk <= 0:
                continue
            rr1 = abs(price - tp1) / risk
            rr2 = abs(price - tp2) / risk

            if rr1 < 2.0 and rr2 < 2.0:
                continue

            best_rr = max(rr1, rr2)

            reasons = []
            if bearish_candles:
                reasons.append(bearish_candles[0]["name"])
            if near_resistance and level_name:
                reasons.append(level_name)
            elif bb_rejection:
                reasons.append("BB rejection")
            reasons.extend(mom_sell_reasons[:2])
            if vol_confirmed:
                reasons.append("Vol ✓")

            confidence = _calculate_signal_confidence(
                total_sell, trend, vol_confirmed, best_rr, "exit"
            )

            raw_signals.append({
                "idx": i, "date": date, "price": round(price, 2),
                "type": "exit",
                "reason": " · ".join(reasons[:4]),
                "confidence": confidence,
                "total_factors": total_sell,
                "trend": trend,
                "stop": round(stop, 2),
                "tp1": round(tp1, 2),
                "tp2": round(tp2, 2),
                "target": round(tp1, 2),
                "rr": round(best_rr, 1),
            })

    # ════════════════════════════════════════════════════════════
    # POST-PROCESSING
    # ════════════════════════════════════════════════════════════

    # Phase 1: Alternating buy/sell, minimum 25-day gap
    alternating = []
    last_type = None
    last_idx = -100
    for sig in raw_signals:
        gap = sig["idx"] - last_idx
        if sig["type"] == last_type:
            if alternating and sig["confidence"] > alternating[-1]["confidence"] + 8 and gap >= 25:
                alternating[-1] = sig
                last_idx = sig["idx"]
            continue
        if gap < 25:
            continue
        alternating.append(sig)
        last_type = sig["type"]
        last_idx = sig["idx"]

    # Phase 2: Forced exits (stop-loss breach or 10% drawdown)
    final = []
    for idx_s, sig in enumerate(alternating):
        final.append(sig)
        if sig["type"] != "entry":
            continue

        entry_bar = sig["idx"]
        stop_level = sig.get("stop")
        entry_price = sig["price"]
        next_bar = alternating[idx_s + 1]["idx"] if idx_s + 1 < len(alternating) else n

        forced_exit_bar = None
        forced_reason = None
        consecutive_below_stop = 0
        for j in range(entry_bar + 1, min(next_bar, n)):
            p = float(close.iloc[j])
            # Stop-loss: require 2 consecutive daily closes below stop
            if stop_level is not None and p < stop_level:
                consecutive_below_stop += 1
                if consecutive_below_stop >= 2:
                    forced_exit_bar = j
                    forced_reason = f"Stop hit ₹{stop_level:.0f}"
                    break
            else:
                consecutive_below_stop = 0
            # Hard exit: price drops >12% from entry
            if entry_price > 0 and (entry_price - p) / entry_price > 0.12:
                forced_exit_bar = j
                pct = (entry_price - p) / entry_price * 100
                forced_reason = f"Down {pct:.0f}% from entry"
                break

        if forced_exit_bar is not None and forced_exit_bar < next_bar:
            dt = str(df.index[forced_exit_bar].date()) if hasattr(df.index[forced_exit_bar], "date") else str(df.index[forced_exit_bar])
            exit_price = float(close.iloc[forced_exit_bar])
            final.append({
                "idx": forced_exit_bar, "date": dt,
                "price": round(exit_price, 2),
                "type": "exit",
                "reason": forced_reason,
                "confidence": 90,
                "total_factors": 0, "trend": "forced",
                "stop": None, "tp1": None, "tp2": None,
                "target": None, "rr": None,
            })

    # Phase 3: Clean alternation
    cleaned = []
    prev_type = None
    for sig in final:
        if sig["type"] == prev_type:
            if sig.get("trend") == "forced":
                cleaned[-1] = sig
        else:
            cleaned.append(sig)
            prev_type = sig["type"]

    result = []
    for sig in cleaned[-15:]:
        strength = "strong" if sig["confidence"] >= 75 else "moderate"
        result.append({
            "date": sig["date"],
            "price": sig["price"],
            "type": sig["type"],
            "reason": sig["reason"],
            "strength": strength,
            "confidence": sig["confidence"],
            "stop": sig.get("stop"),
            "tp1": sig.get("tp1"),
            "tp2": sig.get("tp2"),
            "target": sig.get("target"),
            "rr": sig.get("rr"),
        })
    return result


def _calculate_signal_confidence(total_factors: int, trend: str,
                                  vol_confirmed: bool, rr_ratio: float,
                                  signal_type: str) -> int:
    """
    Confidence score based on confluence count.

      3 factors (minimum):  55-60%
      4 factors:            65-70%
      5 factors:            72-78%
      6+ factors:           80-88%

    Boosted by: strong trend alignment, volume, high RRR.
    """
    base = 45 + total_factors * 6

    if signal_type == "entry":
        if trend == "strong_uptrend":
            base += 12
        elif trend == "uptrend":
            base += 6
    else:
        if trend == "strong_downtrend":
            base += 12
        elif trend == "downtrend":
            base += 6

    if vol_confirmed:
        base += 4

    if rr_ratio >= 3.5:
        base += 6
    elif rr_ratio >= 2.5:
        base += 3

    return min(92, max(35, base))
