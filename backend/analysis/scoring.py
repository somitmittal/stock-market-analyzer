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
    Returns current recommendation, historical signals, score trend, and reasoning.
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

    # Live score trend + pump-and-dump detection
    score_trend = _compute_live_score_trend(df)
    pump_dump = _detect_pump_and_dump(df)

    # Adjust composite if pump-and-dump detected
    if pump_dump["detected"]:
        composite = min(composite, 55)
        entry_probability = min(55, entry_probability)

    action = _determine_action(entry_probability, tech_score, fundamental_analysis,
                               pump_dump_detected=pump_dump["detected"])

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
        "score_trend": score_trend,
        "pump_dump_risk": pump_dump,
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


def _determine_action(probability: float, tech_score: dict, fund_analysis: dict,
                      pump_dump_detected: bool = False) -> str:
    """
    STRONG BUY requires ALL of:
      1. Composite score >= 80
      2. Technical score >= 75 (multiple indicators must agree)
      3. Fundamentals not negative (>= 45)
      4. At least 4 bullish technical signals firing
      5. NOT a pump-and-dump pattern
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

    if pump_dump_detected:
        return "HOLD"

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


def _compute_live_score_trend(df: pd.DataFrame, lookback: int = 20) -> dict:
    """
    Compute a rolling buy/sell strength score for each of the last `lookback`
    bars. Tracks how momentum is building up or dissipating in real time.

    Each bar gets a score from -100 (extreme bearish) to +100 (extreme bullish)
    based on: EMA alignment, RSI, MACD, volume direction + magnitude, and
    price position.

    Returns:
      direction: "strengthening" | "stable" | "weakening"
      current_score: latest bar score
      momentum_shift: True if score changed > 30 pts in last 5 bars
      volume_surge: True if abnormal buying volume in last 3 bars
      bars: list of {date, score, volume_signal} for each bar
    """
    import ta as ta_lib

    n = len(df)
    if n < 50:
        return {"direction": "stable", "current_score": 0,
                "momentum_shift": False, "volume_surge": False, "bars": []}

    close = df["Close"]
    open_ = df["Open"]
    volume = df["Volume"]

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    rsi = ta_lib.momentum.RSIIndicator(close, window=14).rsi()
    macd_ind = ta_lib.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_line = macd_ind.macd()
    macd_signal = macd_ind.macd_signal()
    vol_ma10 = volume.rolling(10).mean()
    vol_max_60 = volume.rolling(60).max()

    start = max(0, n - lookback)
    bars = []

    for i in range(start, n):
        score = 0
        p = float(close.iloc[i])
        e20 = float(ema20.iloc[i]) if not pd.isna(ema20.iloc[i]) else p
        e50 = float(ema50.iloc[i]) if not pd.isna(ema50.iloc[i]) else p

        if p > e20:
            score += 12
        else:
            score -= 12
        if p > e50:
            score += 12
        else:
            score -= 12
        if e20 > e50:
            score += 8
        else:
            score -= 8

        r = float(rsi.iloc[i]) if not pd.isna(rsi.iloc[i]) else 50
        if r < 30:
            score += 15
        elif r < 40:
            score += 8
        elif r > 70:
            score -= 15
        elif r > 60:
            score -= 8

        ml = float(macd_line.iloc[i]) if not pd.isna(macd_line.iloc[i]) else 0
        ms = float(macd_signal.iloc[i]) if not pd.isna(macd_signal.iloc[i]) else 0
        if ml > ms:
            score += 10
        elif ml < ms:
            score -= 10
        if ml > 0:
            score += 5
        elif ml < 0:
            score -= 5

        cur_v = float(volume.iloc[i]) if not pd.isna(volume.iloc[i]) else 0
        avg_v = float(vol_ma10.iloc[i]) if not pd.isna(vol_ma10.iloc[i]) else 0
        max_v = float(vol_max_60.iloc[i]) if not pd.isna(vol_max_60.iloc[i]) else 0
        is_green = float(close.iloc[i]) > float(open_.iloc[i])

        vol_signal = "normal"
        if avg_v > 0 and cur_v > avg_v * 1.5:
            if is_green:
                score += 18
                vol_signal = "high_buy"
            else:
                score -= 18
                vol_signal = "high_sell"

            if max_v > 0 and cur_v >= max_v * 0.85:
                if is_green:
                    score += 10
                    vol_signal = "surge_buy"
                else:
                    score -= 10
                    vol_signal = "surge_sell"
        elif avg_v > 0 and cur_v > avg_v:
            if is_green:
                score += 5
            else:
                score -= 5

        score = max(-100, min(100, score))

        dt = str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i])
        bars.append({"date": dt, "score": score, "volume_signal": vol_signal})

    if len(bars) < 2:
        return {"direction": "stable", "current_score": 0,
                "momentum_shift": False, "volume_surge": False, "bars": bars}

    current_score = bars[-1]["score"]

    recent_5 = bars[-5:] if len(bars) >= 5 else bars
    score_change = recent_5[-1]["score"] - recent_5[0]["score"]
    if score_change > 25:
        direction = "strengthening"
    elif score_change < -25:
        direction = "weakening"
    else:
        direction = "stable"

    momentum_shift = abs(score_change) > 30

    recent_3_vol = [b["volume_signal"] for b in bars[-3:]]
    volume_surge = any(v in ("surge_buy", "high_buy") for v in recent_3_vol)

    return {
        "direction": direction,
        "current_score": current_score,
        "momentum_shift": momentum_shift,
        "volume_surge": volume_surge,
        "bars": bars,
    }


def _detect_pump_and_dump(df: pd.DataFrame) -> dict:
    """
    Detect pump-and-dump patterns to suppress false strong buy signals.

    A P&D is identified by the simultaneous presence of:
    1. Rapid price surge (>20% in 5 bars or >30% in 10 bars)
    2. Price extended far above moving averages (>15% above 50 EMA)
    3. RSI deeply overbought (>80)
    4. Extreme volume spike (near yearly highs)
    5. No prior accumulation pattern (volume was low before the spike)

    Returns dict with: detected, risk_level, reasons, confidence_penalty
    """
    import ta as ta_lib

    n = len(df)
    if n < 60:
        return {"detected": False, "risk_level": "none", "reasons": [], "confidence_penalty": 0}

    close = df["Close"]
    open_ = df["Open"]
    volume = df["Volume"]
    high = df["High"]

    cur_price = float(close.iloc[-1])
    ema50 = close.ewm(span=50, adjust=False).mean()
    rsi = ta_lib.momentum.RSIIndicator(close, window=14).rsi()
    vol_ma20 = volume.rolling(20).mean()
    vol_max_250 = volume.rolling(min(250, n)).max()

    reasons = []
    risk_score = 0

    price_5d_ago = float(close.iloc[-6]) if n >= 6 else cur_price
    price_10d_ago = float(close.iloc[-11]) if n >= 11 else cur_price
    change_5d = (cur_price - price_5d_ago) / price_5d_ago * 100 if price_5d_ago > 0 else 0
    change_10d = (cur_price - price_10d_ago) / price_10d_ago * 100 if price_10d_ago > 0 else 0

    if change_5d > 30:
        risk_score += 4
        reasons.append(f"Price surged {change_5d:.0f}% in 5 days")
    elif change_5d > 20:
        risk_score += 3
        reasons.append(f"Price up {change_5d:.0f}% in 5 days")
    elif change_10d > 30:
        risk_score += 2
        reasons.append(f"Price up {change_10d:.0f}% in 10 days")

    e50 = float(ema50.iloc[-1]) if not pd.isna(ema50.iloc[-1]) else cur_price
    extension_pct = (cur_price - e50) / e50 * 100 if e50 > 0 else 0
    if extension_pct > 25:
        risk_score += 3
        reasons.append(f"Price {extension_pct:.0f}% above 50 EMA (extreme)")
    elif extension_pct > 15:
        risk_score += 2
        reasons.append(f"Price {extension_pct:.0f}% above 50 EMA (extended)")

    cur_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
    if cur_rsi > 85:
        risk_score += 3
        reasons.append(f"RSI at {cur_rsi:.0f} (extreme overbought)")
    elif cur_rsi > 80:
        risk_score += 2
        reasons.append(f"RSI at {cur_rsi:.0f} (overbought)")

    cur_vol = float(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else 0
    avg_vol = float(vol_ma20.iloc[-1]) if not pd.isna(vol_ma20.iloc[-1]) else 0
    max_vol = float(vol_max_250.iloc[-1]) if not pd.isna(vol_max_250.iloc[-1]) else 0

    if max_vol > 0 and cur_vol >= max_vol * 0.9:
        risk_score += 2
        reasons.append("Volume at yearly high")
    elif avg_vol > 0 and cur_vol > avg_vol * 3:
        risk_score += 2
        reasons.append(f"Volume {cur_vol/avg_vol:.1f}x above average")

    if avg_vol > 0 and n >= 30:
        pre_spike_vol = volume.iloc[-30:-6]
        pre_avg = float(pre_spike_vol.mean()) if len(pre_spike_vol) > 0 else avg_vol
        recent_avg = float(volume.iloc[-5:].mean())
        if pre_avg > 0 and recent_avg > pre_avg * 3:
            risk_score += 2
            reasons.append("Volume spike after quiet period (P&D pattern)")

    recent_5_red = sum(
        1 for j in range(-5, 0)
        if float(close.iloc[j]) < float(open_.iloc[j])
    )
    if change_5d > 15 and recent_5_red >= 3:
        risk_score += 1
        reasons.append("Choppy rise with many red candles (distribution)")

    if risk_score >= 8:
        risk_level = "high"
        penalty = -30
    elif risk_score >= 5:
        risk_level = "medium"
        penalty = -20
    elif risk_score >= 3:
        risk_level = "low"
        penalty = -10
    else:
        return {"detected": False, "risk_level": "none", "reasons": [], "confidence_penalty": 0}

    return {
        "detected": True,
        "risk_level": risk_level,
        "reasons": reasons,
        "confidence_penalty": penalty,
    }


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


def _compute_weekly_trend(df: pd.DataFrame) -> pd.Series:
    """
    Resample daily data to weekly, compute weekly EMA50/200 trend,
    then forward-fill back to daily index.
    Returns a Series aligned to daily index with values:
      "strong_uptrend", "uptrend", "neutral", "downtrend", "strong_downtrend"
    """
    weekly = df.resample("W").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna(subset=["Close"])

    if len(weekly) < 50:
        return pd.Series("neutral", index=df.index)

    wc = weekly["Close"]
    w_ema50 = wc.ewm(span=50, adjust=False).mean()
    w_ema200 = wc.ewm(span=200, adjust=False).mean() if len(weekly) >= 200 else pd.Series(np.nan, index=weekly.index)

    labels = []
    for i in range(len(weekly)):
        p = float(wc.iloc[i])
        e50 = float(w_ema50.iloc[i]) if not pd.isna(w_ema50.iloc[i]) else None
        e200 = float(w_ema200.iloc[i]) if not pd.isna(w_ema200.iloc[i]) else None

        bull, bear = 0, 0
        if e50 is not None:
            if p > e50:
                bull += 1
            else:
                bear += 1
        if e200 is not None:
            if p > e200:
                bull += 1
            else:
                bear += 1
        if e50 is not None and e200 is not None:
            if e50 > e200:
                bull += 1
            else:
                bear += 1

        net = bull - bear
        if net >= 3:
            labels.append("strong_uptrend")
        elif net >= 1:
            labels.append("uptrend")
        elif net <= -3:
            labels.append("strong_downtrend")
        elif net <= -1:
            labels.append("downtrend")
        else:
            labels.append("neutral")

    weekly_trend = pd.Series(labels, index=weekly.index)
    return weekly_trend.reindex(df.index, method="ffill").fillna("neutral")


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

def _build_sr_zones(high: pd.Series, low: pd.Series,
                    swing_highs: pd.Series, swing_lows: pd.Series,
                    i: int, price: float, atr_val: float
                    ) -> tuple[list[dict], list[dict]]:
    """
    Build clustered S/R zones from swing points in the last 200 bars.
    Levels within 1.5% of each other are grouped into a zone.
    Each zone has: center, touches (strength), most_recent bar index.
    Returns (support_zones_below, resistance_zones_above) sorted by proximity.
    """
    raw_supports = []
    raw_resistances = []
    lookback = min(i, 200)
    for j in range(i - lookback, i):
        if j < 0:
            continue
        if swing_lows.iloc[j]:
            lvl = float(low.iloc[j])
            if lvl < price:
                raw_supports.append((lvl, j))
        if swing_highs.iloc[j]:
            lvl = float(high.iloc[j])
            if lvl > price:
                raw_resistances.append((lvl, j))

    support_zones = _cluster_levels(raw_supports, price, pct_band=0.015)
    resistance_zones = _cluster_levels(raw_resistances, price, pct_band=0.015)

    support_zones.sort(key=lambda z: price - z["center"])
    resistance_zones.sort(key=lambda z: z["center"] - price)

    return support_zones, resistance_zones


def _cluster_levels(levels: list[tuple[float, int]], price: float, pct_band: float = 0.015) -> list[dict]:
    """Cluster price levels within pct_band of each other into zones."""
    if not levels:
        return []
    levels_sorted = sorted(levels, key=lambda x: x[0])
    zones = []
    current_group = [levels_sorted[0]]
    for lvl, idx in levels_sorted[1:]:
        if current_group and abs(lvl - current_group[0][0]) / max(current_group[0][0], 1) <= pct_band:
            current_group.append((lvl, idx))
        else:
            zones.append(_make_zone(current_group))
            current_group = [(lvl, idx)]
    if current_group:
        zones.append(_make_zone(current_group))
    return zones


def _make_zone(group: list[tuple[float, int]]) -> dict:
    prices = [g[0] for g in group]
    indices = [g[1] for g in group]
    return {
        "center": sum(prices) / len(prices),
        "touches": len(group),
        "most_recent": max(indices),
    }


def _find_nearest_sr(support_zones: list[dict], resistance_zones: list[dict],
                     price: float) -> tuple[float | None, float | None, int, int]:
    """
    Get nearest support and resistance from clustered zones.
    Returns (support_price, resistance_price, support_touches, resistance_touches).
    """
    support = support_zones[0]["center"] if support_zones else None
    resistance = resistance_zones[0]["center"] if resistance_zones else None
    s_touches = support_zones[0]["touches"] if support_zones else 0
    r_touches = resistance_zones[0]["touches"] if resistance_zones else 0
    return support, resistance, s_touches, r_touches


def _is_near_key_level(price: float, support: float | None,
                       resistance: float | None, atr_val: float,
                       s_touches: int = 1, r_touches: int = 1
                       ) -> tuple[bool, bool, str | None, int]:
    """
    Check if price is within 1.5 ATR of a key S/R zone.
    Returns (near_support, near_resistance, description, zone_strength).
    Zone strength = number of touches at the level.
    """
    near_support = support is not None and 0 < (price - support) < atr_val * 1.5
    near_resistance = resistance is not None and 0 < (resistance - price) < atr_val * 1.5
    level_name = None
    strength = 1
    if near_support:
        level_name = f"S ₹{support:.0f} ({s_touches}x)"
        strength = s_touches
    elif near_resistance:
        level_name = f"R ₹{resistance:.0f} ({r_touches}x)"
        strength = r_touches
    return near_support, near_resistance, level_name, strength


def _compute_fibonacci_levels(high: pd.Series, low: pd.Series,
                              swing_highs: pd.Series, swing_lows: pd.Series,
                              i: int, price: float,
                              lookback: int = 120) -> dict | None:
    """
    Find the most recent significant swing move and compute Fibonacci
    retracement levels (23.6%, 38.2%, 61.8%).

    Returns dict with:
      move_type: "up" or "down"
      swing_low, swing_high: the endpoints of the move
      levels: dict mapping pct label to price
      nearest_level: the Fib level closest to current price (or None)
      distance_pct: how far price is from nearest_level as % of move range
    Returns None if no significant swing move found.
    """
    start = max(0, i - lookback)

    sh_indices = [j for j in range(start, i) if swing_highs.iloc[j]]
    sl_indices = [j for j in range(start, i) if swing_lows.iloc[j]]

    if not sh_indices or not sl_indices:
        return None

    last_sh_idx = sh_indices[-1]
    last_sl_idx = sl_indices[-1]
    swing_h = float(high.iloc[last_sh_idx])
    swing_l = float(low.iloc[last_sl_idx])

    move_range = swing_h - swing_l
    if move_range <= 0 or move_range / swing_l < 0.03:
        return None

    if last_sl_idx < last_sh_idx:
        move_type = "up"
        levels = {
            "23.6%": swing_h - move_range * 0.236,
            "38.2%": swing_h - move_range * 0.382,
            "61.8%": swing_h - move_range * 0.618,
        }
    else:
        move_type = "down"
        levels = {
            "23.6%": swing_l + move_range * 0.236,
            "38.2%": swing_l + move_range * 0.382,
            "61.8%": swing_l + move_range * 0.618,
        }

    nearest_label = None
    nearest_price = None
    min_dist = float("inf")
    for label, lvl in levels.items():
        dist = abs(price - lvl) / move_range
        if dist < min_dist:
            min_dist = dist
            nearest_label = label
            nearest_price = lvl

    PROXIMITY_THRESHOLD = 0.04
    if min_dist > PROXIMITY_THRESHOLD:
        nearest_label = None
        nearest_price = None

    return {
        "move_type": move_type,
        "swing_low": swing_l,
        "swing_high": swing_h,
        "levels": levels,
        "nearest_level": nearest_label,
        "nearest_price": nearest_price,
        "distance_pct": min_dist,
    }


def _detect_range_breakout(close: pd.Series, high: pd.Series, low: pd.Series,
                           volume: pd.Series, vol_ma20: pd.Series,
                           i: int, support: float | None,
                           resistance: float | None,
                           atr_val: float,
                           min_range_bars: int = 20) -> dict | None:
    """
    Detect if stock is breaking out of a consolidation range.

    A range is identified when price has stayed within support-resistance
    boundaries for min_range_bars. A breakout requires:
      1. Price closes above resistance (bullish) or below support (bearish)
      2. Volume is above 20-day average (institutional participation)

    Returns dict with breakout info, or None.
    """
    if support is None or resistance is None:
        return None

    range_width = resistance - support
    if range_width <= 0 or range_width / support < 0.02:
        return None

    start = max(0, i - min_range_bars)
    bars_in_range = 0
    tolerance = atr_val * 0.5
    for j in range(start, i):
        h = float(high.iloc[j])
        l = float(low.iloc[j])
        if l >= support - tolerance and h <= resistance + tolerance:
            bars_in_range += 1

    range_pct = bars_in_range / max(1, i - start)
    if range_pct < 0.65:
        return None

    cur_close = float(close.iloc[i])
    cur_vol = float(volume.iloc[i]) if not pd.isna(volume.iloc[i]) else 0
    avg_vol = float(vol_ma20.iloc[i]) if not pd.isna(vol_ma20.iloc[i]) else 0
    vol_confirm = cur_vol > avg_vol * 1.0 if avg_vol > 0 else False

    if cur_close > resistance:
        return {
            "direction": "bullish",
            "breakout_price": resistance,
            "range_width": range_width,
            "bars_in_range": bars_in_range,
            "volume_confirmed": vol_confirm,
            "target": resistance + range_width,
        }
    elif cur_close < support:
        return {
            "direction": "bearish",
            "breakout_price": support,
            "range_width": range_width,
            "bars_in_range": bars_in_range,
            "volume_confirmed": vol_confirm,
            "target": support - range_width,
        }

    return None


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
    Detect RSI divergence at bar i with strict filters:
    - RSI must be in an extreme zone (< 40 for bullish, > 60 for bearish)
    - Price swing must be meaningful (> 2% difference between lows/highs)
    - RSI difference must be > 3 points (not noise)
    """
    cur_rsi = float(rsi.iloc[i]) if not pd.isna(rsi.iloc[i]) else None
    if cur_rsi is None:
        return None

    # Bullish divergence: only when RSI is in lower territory
    if cur_rsi < 40:
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
                price_diff_pct = (p2 - p1) / p2 * 100 if p2 > 0 else 0
                rsi_diff = r1 - r2
                if p1 < p2 and price_diff_pct > 2.0 and rsi_diff > 3:
                    return "bullish"

    # Bearish divergence: only when RSI is in upper territory
    if cur_rsi > 60:
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
                price_diff_pct = (p1 - p2) / p2 * 100 if p2 > 0 else 0
                rsi_diff = r2 - r1
                if p1 > p2 and price_diff_pct > 2.0 and rsi_diff > 3:
                    return "bearish"

    return None


# ═══════════════════════════════════════════════════════════════════
# MAIN SIGNAL ENGINE — 3-FACTOR CONFLUENCE
# ═══════════════════════════════════════════════════════════════════

def _generate_historical_signals(df: pd.DataFrame, technical: dict) -> list[dict]:
    """
    Institutional-grade signal engine v2 with 7 improvements:

    1. TRAILING STOP — SL moves to breakeven at +1R, trails at 2x ATR
    2. MULTI-TIMEFRAME — weekly trend must align with daily entry
    3. CLUSTERED S/R ZONES — multi-touch levels scored by strength
    4. CONTEXT-WEIGHTED PATTERNS — candles at key levels count more
    5. VOLATILITY REGIME — BB squeeze boosts, chop suppresses
    6. TIGHTER RSI DIVERGENCE — extreme zone + meaningful swing required
    7. BROAD MARKET FILTER — suppresses entries during index downtrends

    Core confluence logic unchanged: need factors from all 3 categories.
    """
    import ta as ta_lib

    close = df["Close"]
    open_ = df["Open"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    n = len(df)

    # ── ADAPTIVE MODE for small-caps / limited-history stocks ──
    # Determine regime based on available data length
    if n >= 500:
        # Full mode: EMA50/200, 200-bar warmup
        ema_short_span = 50
        ema_long_span = 200
        warmup = 200
        min_gap = 20
    elif n >= 250:
        # Medium mode: EMA30/100, 100-bar warmup
        ema_short_span = 30
        ema_long_span = 100
        warmup = 100
        min_gap = 15
    elif n >= 120:
        # Short mode: EMA20/50, 60-bar warmup
        ema_short_span = 20
        ema_long_span = 50
        warmup = 60
        min_gap = 10
    else:
        return []

    # Detect if this is a high-volatility stock (small-cap proxy):
    # median daily range as % of close over last 60 bars
    recent_window = min(n, 60)
    recent_range_pct = ((high.iloc[-recent_window:] - low.iloc[-recent_window:])
                        / close.iloc[-recent_window:]).median()
    is_high_vol = recent_range_pct > 0.035  # >3.5% daily range = high vol

    # Wider stops and higher drawdown tolerance for volatile stocks
    atr_stop_mult = 3.0 if is_high_vol else 2.5
    drawdown_limit = 0.15 if is_high_vol else 0.12

    # ── Compute all indicators ──
    rsi = ta_lib.momentum.RSIIndicator(close, window=14).rsi()
    macd_ind = ta_lib.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_line = macd_ind.macd()
    macd_signal_line = macd_ind.macd_signal()
    bb = ta_lib.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_lower = bb.bollinger_lband()
    bb_upper = bb.bollinger_hband()
    bb_bandwidth = bb.bollinger_wband()
    stoch = ta_lib.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
    stoch_k = stoch.stoch()
    stoch_d = stoch.stoch_signal()
    atr_ind = ta_lib.volatility.AverageTrueRange(high, low, close, window=14)
    atr = atr_ind.average_true_range()

    ema_short = close.ewm(span=ema_short_span, adjust=False).mean()
    ema_long = close.ewm(span=ema_long_span, adjust=False).mean()
    # Keep ema50/ema200 names for _classify_trend interface
    ema50 = ema_short
    ema200 = ema_long
    vol_ma20 = volume.rolling(20).mean()
    # Rolling max volume for abnormality detection across multiple timeframes
    vol_max_20 = volume.rolling(20).max()    # ~1 month
    vol_max_60 = volume.rolling(60).max()    # ~3 months
    vol_max_120 = volume.rolling(120).max()  # ~6 months
    vol_max_250 = volume.rolling(250).max()  # ~1 year

    swing_highs, swing_lows = _detect_swing_points(high, low, lookback=5)

    # ── Multi-timeframe — weekly trend (skip if insufficient data) ──
    if n >= 250:
        weekly_trend = _compute_weekly_trend(df)
    else:
        weekly_trend = pd.Series("neutral", index=df.index)

    # ── Volatility regime — BB bandwidth percentile ──
    bw_percentile = bb_bandwidth.rank(pct=True)

    raw_signals = []

    for i in range(warmup, n):
        price = float(close.iloc[i])
        date = str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i])
        cur_atr = float(atr.iloc[i]) if not pd.isna(atr.iloc[i]) else price * 0.02

        # ── IMPROVEMENT 2: Weekly trend filter ──
        wt = weekly_trend.iloc[i] if i < len(weekly_trend) else "neutral"
        weekly_bullish = wt in ("strong_uptrend", "uptrend", "neutral")
        # For sells: allow when weekly is bearish/neutral OR when daily
        # trend is already bearish (daily breakdown overrides weekly lag)
        weekly_bearish = wt in ("strong_downtrend", "downtrend", "neutral")

        # ════════════════════════════════════════════════════════════
        # CATEGORY 1: TREND & CONTEXT
        # ════════════════════════════════════════════════════════════
        trend_info = _classify_trend(
            price, ema50, ema200, swing_highs, swing_lows,
            high, low, close, i
        )
        trend = trend_info["trend"]
        is_bearish = trend in ("strong_downtrend", "downtrend")
        is_bullish = trend in ("strong_uptrend", "uptrend")

        trend_buy_score = trend_info["bullish_factors"]
        trend_sell_score = trend_info["bearish_factors"]
        has_trend_buy = trend_buy_score >= 2 and not is_bearish and weekly_bullish
        has_trend_sell = trend_sell_score >= 2 and not is_bullish and (weekly_bearish or is_bearish)

        # ════════════════════════════════════════════════════════════
        # CATEGORY 2: PRICE ACTION & LEVELS (IMPROVED — clustered S/R)
        # ════════════════════════════════════════════════════════════
        support_zones, resistance_zones = _build_sr_zones(
            high, low, swing_highs, swing_lows, i, price, cur_atr
        )
        support, resistance, s_touches, r_touches = _find_nearest_sr(
            support_zones, resistance_zones, price
        )
        near_support, near_resistance, level_name, zone_strength = _is_near_key_level(
            price, support, resistance, cur_atr, s_touches, r_touches
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

        # ── Breakdown detection (sell-side PA) ──
        # Price breaking below support = sell PA signal
        support_breakdown = (support is not None and price < support
                             and float(close.iloc[i-1]) >= support)
        # Price crossing below 50 EMA (was above within last 3 bars)
        ema50_breakdown = False
        e50_now = float(ema50.iloc[i]) if not pd.isna(ema50.iloc[i]) else None
        if e50_now is not None and price < e50_now:
            for jj in range(max(0, i - 3), i):
                if float(close.iloc[jj]) > float(ema50.iloc[jj]):
                    ema50_breakdown = True
                    break

        # ── IMPROVEMENT 4: Context-weighted patterns ──
        # Patterns at multi-touch zones (3+ touches) count double
        candle_weight = 2 if zone_strength >= 3 else 1
        pa_buy_score = (
            int(near_support) * min(zone_strength, 3)
            + int(len(bullish_candles) > 0) * candle_weight
            + int(bb_reclaim)
        )
        pa_sell_score = (
            int(near_resistance) * min(zone_strength, 3)
            + int(len(bearish_candles) > 0) * candle_weight
            + int(bb_rejection)
            + int(support_breakdown) * 2
            + int(ema50_breakdown)
        )

        # ── Fibonacci retracement confluence ──
        fib_info = _compute_fibonacci_levels(
            high, low, swing_highs, swing_lows, i, price
        )
        fib_at_level = False
        fib_label = None
        if fib_info and fib_info["nearest_level"] is not None:
            fib_label = fib_info["nearest_level"]
            if fib_info["move_type"] == "up" and bullish_candles:
                pa_buy_score += 2
                fib_at_level = True
            elif fib_info["move_type"] == "down" and bearish_candles:
                pa_sell_score += 2
                fib_at_level = True
            elif fib_info["move_type"] == "up":
                pa_buy_score += 1
            elif fib_info["move_type"] == "down":
                pa_sell_score += 1

        # ── Range breakout detection ──
        breakout = _detect_range_breakout(
            close, high, low, volume, vol_ma20, i,
            support, resistance, cur_atr, min_range_bars=20
        )
        breakout_buy = False
        breakout_sell = False
        if breakout is not None:
            if breakout["direction"] == "bullish":
                pa_buy_score += 2
                if breakout["volume_confirmed"]:
                    pa_buy_score += 1
                breakout_buy = True
            elif breakout["direction"] == "bearish":
                pa_sell_score += 2
                if breakout["volume_confirmed"]:
                    pa_sell_score += 1
                breakout_sell = True

        has_pa_buy = pa_buy_score >= 1
        has_pa_sell = pa_sell_score >= 1

        # ════════════════════════════════════════════════════════════
        # CATEGORY 3: MOMENTUM & VOLUME
        # ════════════════════════════════════════════════════════════
        mom_buy_score = 0
        mom_sell_score = 0
        mom_buy_reasons = []
        mom_sell_reasons = []

        if not pd.isna(rsi.iloc[i]) and not pd.isna(rsi.iloc[i-1]):
            r_now, r_prev = float(rsi.iloc[i]), float(rsi.iloc[i-1])
            if r_now < 20:
                mom_buy_score += 2
                mom_buy_reasons.append(f"RSI {r_now:.0f} extreme")
            elif r_now < 25:
                mom_buy_score += 1
                mom_buy_reasons.append(f"RSI {r_now:.0f} deeply oversold")
            if r_prev < 30 and r_now >= 30:
                mom_buy_score += 1
                mom_buy_reasons.append("RSI ↑30")
            elif r_prev < 40 and r_now >= 40 and r_prev > 25:
                mom_buy_score += 1
                mom_buy_reasons.append("RSI recovering")
            if r_now > 80:
                mom_sell_score += 2
                mom_sell_reasons.append(f"RSI {r_now:.0f} extreme")
            elif r_now > 75:
                mom_sell_score += 1
                mom_sell_reasons.append(f"RSI {r_now:.0f} deeply overbought")
            if r_prev > 70 and r_now <= 70:
                mom_sell_score += 1
                mom_sell_reasons.append("RSI ↓70")
            elif r_prev > 60 and r_now <= 60 and r_prev < 75:
                mom_sell_score += 1
                mom_sell_reasons.append("RSI weakening")
            # Sustained declining momentum: RSI falling below 45 from above
            if r_prev >= 45 and r_now < 45:
                mom_sell_score += 1
                mom_sell_reasons.append("RSI ↓45")
            elif r_prev >= 35 and r_now < 35:
                mom_sell_score += 1
                mom_sell_reasons.append("RSI ↓35")

        div = _detect_rsi_divergence(close, rsi, swing_lows, swing_highs, low, high, i)
        if div == "bullish":
            mom_buy_score += 1
            mom_buy_reasons.append("RSI bull div")
        elif div == "bearish":
            mom_sell_score += 1
            mom_sell_reasons.append("RSI bear div")

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
            # MACD crossing below zero = bearish momentum shift
            if ml_p >= 0 and ml < 0:
                mom_sell_score += 1
                mom_sell_reasons.append("MACD ↓0")
            elif ml_p <= 0 and ml > 0:
                mom_buy_score += 1
                mom_buy_reasons.append("MACD ↑0")

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

        # ── Volume analysis — magnitude + direction ──
        # Normal volume = no signal. Abnormally high volume = check direction.
        # Abnormal = approaching or exceeding multi-week/month/year highs.
        vol_confirmed = False
        vol_bearish_pressure = False
        is_green_candle = float(close.iloc[i]) > float(open_.iloc[i])

        cur_v = float(volume.iloc[i]) if not pd.isna(volume.iloc[i]) else 0
        avg_v = float(vol_ma20.iloc[i]) if not pd.isna(vol_ma20.iloc[i]) else 0

        # How abnormal is today's volume? Compare to rolling max at different windows
        vol_abnormality = 0  # 0=normal, 1=high(monthly), 2=very high(quarterly), 3=extreme(yearly)
        if cur_v > 0 and avg_v > 0:
            m20 = float(vol_max_20.iloc[i]) if not pd.isna(vol_max_20.iloc[i]) else 0
            m60 = float(vol_max_60.iloc[i]) if not pd.isna(vol_max_60.iloc[i]) else 0
            m120 = float(vol_max_120.iloc[i]) if not pd.isna(vol_max_120.iloc[i]) else 0
            m250 = float(vol_max_250.iloc[i]) if not pd.isna(vol_max_250.iloc[i]) else 0

            if m250 > 0 and cur_v >= m250 * 0.85:
                vol_abnormality = 3
            elif m120 > 0 and cur_v >= m120 * 0.85:
                vol_abnormality = 2
            elif m60 > 0 and cur_v >= m60 * 0.85:
                vol_abnormality = 1

        if vol_abnormality >= 1:
            if is_green_candle:
                # Abnormally high BUYING volume = strong buy confirmation
                vol_confirmed = True
                mom_buy_score += vol_abnormality
                if vol_abnormality >= 3:
                    mom_buy_reasons.append("Extreme buy vol")
                elif vol_abnormality >= 2:
                    mom_buy_reasons.append("Heavy buy vol")
                else:
                    mom_buy_reasons.append("High buy vol")
            else:
                # Abnormally high SELLING volume = institutional distribution
                mom_sell_score += vol_abnormality
                if vol_abnormality >= 3:
                    mom_sell_reasons.append("Extreme sell vol")
                elif vol_abnormality >= 2:
                    mom_sell_reasons.append("Heavy sell vol")
                else:
                    mom_sell_reasons.append("High sell vol")

        # Check for sustained selling pressure over recent days:
        # Look at last 10 bars — if multiple have abnormally high RED volume
        lookback_vol = min(i, 10)
        abnormal_red_days = 0
        abnormal_green_days = 0
        for vj in range(i - lookback_vol, i):
            if vj < 0:
                continue
            vj_vol = float(volume.iloc[vj]) if not pd.isna(volume.iloc[vj]) else 0
            vj_m60 = float(vol_max_60.iloc[vj]) if not pd.isna(vol_max_60.iloc[vj]) else 0
            vj_green = float(close.iloc[vj]) > float(open_.iloc[vj])
            if vj_m60 > 0 and vj_vol >= vj_m60 * 0.7:
                if vj_green:
                    abnormal_green_days += 1
                else:
                    abnormal_red_days += 1

        if abnormal_red_days >= 3:
            vol_bearish_pressure = True
            mom_sell_score += 1
            mom_sell_reasons.append(f"Sell pressure ({abnormal_red_days}d)")
        elif abnormal_green_days >= 3 and not vol_confirmed:
            vol_confirmed = True
            mom_buy_score += 1
            mom_buy_reasons.append(f"Buy pressure ({abnormal_green_days}d)")

        has_mom_buy = mom_buy_score >= 1
        has_mom_sell = mom_sell_score >= 1

        # ── IMPROVEMENT 5: Volatility regime ──
        cur_bw_pct = float(bw_percentile.iloc[i]) if not pd.isna(bw_percentile.iloc[i]) else 0.5
        in_squeeze = cur_bw_pct < 0.20
        in_chop = 0.40 < cur_bw_pct < 0.70

        # ── Pump-and-dump suppression for historical buy signals ──
        is_pump = False
        if i >= 10:
            p_5ago = float(close.iloc[i - 5]) if i >= 5 else price
            surge_5d = (price - p_5ago) / p_5ago * 100 if p_5ago > 0 else 0
            e50_val = float(ema50.iloc[i]) if not pd.isna(ema50.iloc[i]) else price
            ext_pct = (price - e50_val) / e50_val * 100 if e50_val > 0 else 0
            r_val = float(rsi.iloc[i]) if not pd.isna(rsi.iloc[i]) else 50
            pd_score = 0
            if surge_5d > 20:
                pd_score += 2
            if ext_pct > 15:
                pd_score += 2
            if r_val > 80:
                pd_score += 2
            if vol_abnormality >= 2 and not is_green_candle:
                pd_score += 1
            if pd_score >= 4:
                is_pump = True

        # ── Contrarian bottoming exception ──
        # When RSI is deeply oversold, allow buy signals even in downtrends.
        # Two tiers:
        #   RSI < 20 (extreme): only need PA signal + green candle or RSI rising
        #   RSI < 25 (deep):    need PA signal + momentum + green candle or RSI rising
        is_contrarian_buy = False
        cur_rsi_val = float(rsi.iloc[i]) if not pd.isna(rsi.iloc[i]) else 50
        prev_rsi_val = float(rsi.iloc[i-1]) if i > 0 and not pd.isna(rsi.iloc[i-1]) else 50
        rsi_recovering = cur_rsi_val > prev_rsi_val

        if not has_trend_buy:
            if cur_rsi_val < 20 and has_pa_buy and (is_green_candle or rsi_recovering):
                is_contrarian_buy = True
            elif (cur_rsi_val < 25
                    and (has_pa_buy or len(bullish_candles) > 0)
                    and has_mom_buy
                    and (is_green_candle or rsi_recovering)):
                is_contrarian_buy = True

        # ════════════════════════════════════════════════════════════
        # CONFLUENCE GATE
        # ════════════════════════════════════════════════════════════
        buy_confluence = has_trend_buy and has_pa_buy and has_mom_buy
        sell_confluence = has_trend_sell and has_pa_sell and has_mom_sell

        if is_contrarian_buy:
            buy_confluence = True

        if is_pump:
            buy_confluence = False

        if not buy_confluence and not sell_confluence:
            continue

        total_buy = trend_buy_score + pa_buy_score + mom_buy_score
        total_sell = trend_sell_score + pa_sell_score + mom_sell_score

        # ════════════════════════════════════════════════════════════
        # EXECUTION: SL, TP1, TP2, RRR check
        # ════════════════════════════════════════════════════════════
        if buy_confluence and total_buy > total_sell:
            swing_stop = (support - cur_atr * 1.5) if support is not None else None
            atr_stop = price - cur_atr * atr_stop_mult
            if swing_stop is not None and swing_stop < price:
                stop = min(swing_stop, atr_stop)
            else:
                stop = atr_stop

            if breakout_buy and breakout is not None:
                tp1 = breakout["target"]
            else:
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

            reasons = []
            if is_contrarian_buy:
                reasons.append(f"Oversold RSI {cur_rsi_val:.0f}")
            if breakout_buy:
                reasons.append("Breakout" + (" +Vol" if breakout["volume_confirmed"] else ""))
            if bullish_candles:
                reasons.append(bullish_candles[0]["name"])
            if fib_at_level and fib_label:
                reasons.append(f"Fib {fib_label}")
            if near_support and level_name:
                reasons.append(level_name)
            elif bb_reclaim:
                reasons.append("BB reclaim")
            reasons.extend(mom_buy_reasons[:2])
            if vol_confirmed:
                reasons.append("Vol ✓")
            if in_squeeze:
                reasons.append("Squeeze")

            confidence = _calculate_signal_confidence(
                total_buy, trend, vol_confirmed, best_rr, "entry",
                wt, zone_strength, in_squeeze, in_chop,
                vol_bearish_pressure, is_green_candle, vol_abnormality,
                fib_at_level=fib_at_level, is_breakout=breakout_buy,
                is_contrarian=is_contrarian_buy,
            )

            raw_signals.append({
                "idx": i, "date": date, "price": round(price, 2),
                "type": "entry",
                "reason": " · ".join(reasons[:5]),
                "confidence": confidence,
                "total_factors": total_buy,
                "trend": trend,
                "stop": round(stop, 2),
                "tp1": round(tp1, 2),
                "tp2": round(tp2, 2),
                "target": round(tp1, 2),
                "rr": round(best_rr, 1),
                "atr_at_entry": cur_atr,
            })

        elif sell_confluence and total_sell > total_buy:
            swing_stop = (resistance + cur_atr * 1.5) if resistance is not None else None
            atr_stop = price + cur_atr * atr_stop_mult
            if swing_stop is not None and swing_stop > price:
                stop = max(swing_stop, atr_stop)
            else:
                stop = atr_stop

            if breakout_sell and breakout is not None:
                tp1 = breakout["target"]
            else:
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
            if support_breakdown:
                reasons.append("Support break")
            if ema50_breakdown:
                reasons.append("Below 50 EMA")
            if breakout_sell:
                reasons.append("Breakdown" + (" +Vol" if breakout["volume_confirmed"] else ""))
            if bearish_candles:
                reasons.append(bearish_candles[0]["name"])
            if fib_at_level and fib_label:
                reasons.append(f"Fib {fib_label}")
            if near_resistance and level_name:
                reasons.append(level_name)
            elif bb_rejection:
                reasons.append("BB rejection")
            reasons.extend(mom_sell_reasons[:2])
            if vol_confirmed:
                reasons.append("Vol ✓")

            confidence = _calculate_signal_confidence(
                total_sell, trend, vol_confirmed, best_rr, "exit",
                wt, zone_strength, in_squeeze, in_chop,
                vol_bearish_pressure, is_green_candle, vol_abnormality,
                fib_at_level=fib_at_level, is_breakout=breakout_sell,
            )

            raw_signals.append({
                "idx": i, "date": date, "price": round(price, 2),
                "type": "exit",
                "reason": " · ".join(reasons[:5]),
                "confidence": confidence,
                "total_factors": total_sell,
                "trend": trend,
                "stop": round(stop, 2),
                "tp1": round(tp1, 2),
                "tp2": round(tp2, 2),
                "target": round(tp1, 2),
                "rr": round(best_rr, 1),
                "atr_at_entry": cur_atr,
            })

    # ════════════════════════════════════════════════════════════
    # POST-PROCESSING
    # ════════════════════════════════════════════════════════════

    # Phase 1: Alternating buy/sell, minimum 20-day gap (adaptive)
    alternating = []
    last_type = None
    last_idx = -100
    for sig in raw_signals:
        gap = sig["idx"] - last_idx
        if sig["type"] == last_type:
            if alternating and sig["confidence"] > alternating[-1]["confidence"] + 8 and gap >= min_gap:
                alternating[-1] = sig
                last_idx = sig["idx"]
            continue
        if gap < min_gap:
            continue
        alternating.append(sig)
        last_type = sig["type"]
        last_idx = sig["idx"]

    # Phase 2: TRAILING STOP (Improvement #1 — the biggest win-rate booster)
    final = []
    for idx_s, sig in enumerate(alternating):
        final.append(sig)
        if sig["type"] != "entry":
            continue

        entry_bar = sig["idx"]
        initial_stop = sig.get("stop")
        entry_price = sig["price"]
        entry_atr = sig.get("atr_at_entry", entry_price * 0.02)
        risk = abs(entry_price - initial_stop) if initial_stop else entry_atr * 2.5
        next_bar = alternating[idx_s + 1]["idx"] if idx_s + 1 < len(alternating) else n

        highest_close = entry_price
        current_stop = initial_stop
        consecutive_below = 0

        forced_exit_bar = None
        forced_reason = None

        for j in range(entry_bar + 1, min(next_bar, n)):
            p = float(close.iloc[j])
            cur_j_atr = float(atr.iloc[j]) if not pd.isna(atr.iloc[j]) else entry_atr

            # Update trailing stop
            if p > highest_close:
                highest_close = p

            profit_from_entry = highest_close - entry_price
            if profit_from_entry >= risk * 2:
                # +2R: trail at highest close minus 2x ATR
                trail_stop = highest_close - cur_j_atr * 2.0
                if current_stop is None or trail_stop > current_stop:
                    current_stop = trail_stop
            elif profit_from_entry >= risk:
                # +1R: move to breakeven (entry price)
                if current_stop is None or entry_price > current_stop:
                    current_stop = entry_price

            # Check stop breach (2 consecutive closes)
            if current_stop is not None and p < current_stop:
                consecutive_below += 1
                if consecutive_below >= 2:
                    forced_exit_bar = j
                    if current_stop > initial_stop and initial_stop is not None:
                        forced_reason = f"Trail stop ₹{current_stop:.0f}"
                    else:
                        forced_reason = f"Stop hit ₹{current_stop:.0f}"
                    break
            else:
                consecutive_below = 0

            # Hard exit: drawdown exceeds limit
            if entry_price > 0 and (entry_price - p) / entry_price > drawdown_limit:
                forced_exit_bar = j
                pct = (entry_price - p) / entry_price * 100
                forced_reason = f"Down {pct:.0f}% from entry"
                break

            # Take-profit exit at TP2
            tp2 = sig.get("tp2")
            if tp2 is not None and p >= tp2:
                forced_exit_bar = j
                pnl_pct = (p - entry_price) / entry_price * 100
                forced_reason = f"TP2 hit +{pnl_pct:.0f}%"
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
                                  signal_type: str,
                                  weekly_trend: str = "neutral",
                                  zone_strength: int = 1,
                                  in_squeeze: bool = False,
                                  in_chop: bool = False,
                                  vol_bearish_pressure: bool = False,
                                  signal_candle_green: bool = True,
                                  vol_abnormality: int = 0,
                                  fib_at_level: bool = False,
                                  is_breakout: bool = False,
                                  is_contrarian: bool = False) -> int:
    """
    Confidence score based on confluence + volume magnitude/direction.
    Abnormal volume (multi-month/year highs) is the strongest signal:
      - Abnormal GREEN volume = institutional buying, big confidence boost
      - Abnormal RED volume = institutional selling, big confidence penalty
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

    if signal_type == "entry" and weekly_trend in ("strong_uptrend", "uptrend"):
        base += 5
    elif signal_type == "exit" and weekly_trend in ("strong_downtrend", "downtrend"):
        base += 5

    # Volume magnitude + direction (the key differentiator)
    if vol_confirmed:
        # Abnormal green volume: scale boost by how extreme it is
        base += 4 + vol_abnormality * 3  # +4 baseline, up to +13 for yearly-high buy vol
    elif signal_type == "entry" and vol_abnormality >= 2 and not signal_candle_green:
        # Abnormally high RED volume on a buy signal = strong penalty
        base -= 10 + vol_abnormality * 4  # up to -22 for yearly-high sell vol
    elif signal_type == "entry" and not signal_candle_green:
        base -= 5

    # Sustained selling pressure over multiple days
    if vol_bearish_pressure:
        if signal_type == "entry":
            base -= 18
        else:
            base += 8

    if rr_ratio >= 3.5:
        base += 6
    elif rr_ratio >= 2.5:
        base += 3

    if zone_strength >= 4:
        base += 6
    elif zone_strength >= 3:
        base += 4
    elif zone_strength >= 2:
        base += 2

    if in_squeeze:
        base += 4
    if in_chop:
        base -= 5

    if fib_at_level:
        base += 5
    if is_breakout:
        base += 6

    if is_contrarian:
        base -= 10
        if vol_confirmed:
            base += 8

    return min(92, max(35, base))
