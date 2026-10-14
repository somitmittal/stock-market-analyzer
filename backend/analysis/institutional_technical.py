"""Institutional-grade technical synthesis for the investment verdict."""

from __future__ import annotations

from typing import Any

from analysis.vcp import detect_vcp


def analyze_institutional_technicals(df, technical: dict[str, Any] | None) -> dict[str, Any]:
    """Synthesize trend, momentum, volume, structure, and pattern evidence."""
    technical = technical or {}
    bull_score = 0
    bear_score = 0
    positives: list[str] = []
    negatives: list[str] = []
    highlights: list[str] = []

    trend = technical.get("trend") or {}
    ma = technical.get("moving_averages") or {}
    rsi = technical.get("rsi") or {}
    macd = technical.get("macd") or {}
    adx = technical.get("adx") or {}
    bollinger = technical.get("bollinger") or {}
    volume = technical.get("volume_analysis") or {}
    sr = technical.get("support_resistance") or {}
    atr = technical.get("atr") or {}
    stochastic = technical.get("stochastic") or {}
    patterns = technical.get("candlestick_patterns") or []

    current_price = float(df["Close"].iloc[-1]) if df is not None and len(df) else None

    # ── 1. Primary trend & moving-average structure ──
    long_trend = trend.get("long")
    medium_trend = trend.get("medium")
    short_trend = trend.get("short")
    if long_trend == "uptrend" and medium_trend == "uptrend":
        bull_score += 2
        positives.append("Primary and intermediate trends are aligned to the upside (institutional trend-follow bias).")
    elif long_trend == "downtrend" and medium_trend == "downtrend":
        bear_score += 2
        negatives.append("Primary and intermediate trends are aligned to the downside.")
    elif long_trend == "uptrend":
        positives.append("Long-term trend remains constructive despite shorter-term noise.")
        bull_score += 1
    elif long_trend == "downtrend":
        negatives.append("Long-term trend is still down — rallies may be sold into.")
        bear_score += 1

    ma_overall = ma.get("overall")
    if ma_overall == "strong_bullish":
        bull_score += 2
        positives.append("Price is above all major SMAs (9/20/50/100/200) — classic stage-2 structure.")
    elif ma_overall == "bullish":
        bull_score += 1
        positives.append("Price trades above most key moving averages.")
    elif ma_overall == "bearish":
        bear_score += 1
        negatives.append("Price is below most key moving averages.")

    cross = ma.get("cross")
    if cross == "golden_cross":
        bull_score += 2
        positives.append("Fresh golden cross (50 SMA crossing above 200 SMA) — major bullish regime shift.")
    elif cross == "death_cross":
        bear_score += 2
        negatives.append("Death cross in play (50 SMA below 200 SMA) — avoid fighting the primary trend.")

    sma200 = (ma.get("sma") or {}).get("200")
    if sma200 and current_price:
        if current_price > sma200["value"]:
            bull_score += 1
            positives.append(f"Trading above 200 SMA (₹{sma200['value']:.2f}) — institutions often use this as the bull/bear line.")
        else:
            bear_score += 1
            negatives.append(f"Trading below 200 SMA (₹{sma200['value']:.2f}).")

    # ── 2. Trend strength (ADX) ──
    adx_val = adx.get("adx")
    adx_strength = adx.get("trend_strength")
    adx_dir = adx.get("direction")
    if adx_strength in ("strong", "very_strong") and adx_dir == "bullish":
        bull_score += 2
        positives.append(f"ADX at {adx_val:.1f} confirms a strong bullish trend (+DI leading).")
    elif adx_strength in ("strong", "very_strong") and adx_dir == "bearish":
        bear_score += 2
        negatives.append(f"ADX at {adx_val:.1f} confirms a strong bearish trend (−DI leading).")
    elif adx_strength == "no_trend":
        highlights.append("ADX shows no dominant trend — range-bound / mean-reversion environment.")

    # ── 3. Momentum cluster (RSI, MACD, Stochastic) ──
    rsi_val = rsi.get("value")
    rsi_signal = rsi.get("signal")
    if rsi_val is not None:
        if rsi_signal == "oversold":
            bull_score += 1
            positives.append(f"RSI {rsi_val:.1f} — oversold; watch for reversal if support holds.")
        elif rsi_signal in ("approaching_oversold",):
            positives.append(f"RSI {rsi_val:.1f} — easing toward oversold.")
            bull_score += 1
        elif rsi_signal == "overbought":
            bear_score += 1
            negatives.append(f"RSI {rsi_val:.1f} — overbought; upside may need consolidation.")
        elif 45 <= rsi_val <= 65:
            positives.append(f"RSI {rsi_val:.1f} — healthy momentum zone, not stretched.")

    divergence = rsi.get("divergence")
    if divergence == "bullish_divergence":
        bull_score += 2
        positives.append("Bullish RSI divergence — price weak but momentum improving (accumulation signal).")
    elif divergence == "bearish_divergence":
        bear_score += 2
        negatives.append("Bearish RSI divergence — price strong but momentum fading.")

    if macd.get("crossover") == "bullish":
        bull_score += 1
        positives.append("MACD bullish crossover — momentum turning up.")
    elif macd.get("crossover") == "bearish":
        bear_score += 1
        negatives.append("MACD bearish crossover — momentum turning down.")
    elif macd.get("trend") == "bullish":
        bull_score += 1
    elif macd.get("trend") == "bearish":
        bear_score += 1

    stoch_signal = stochastic.get("signal")
    if stoch_signal == "oversold":
        bull_score += 1
        positives.append("Stochastic oversold — short-term bounce potential.")
    elif stoch_signal == "overbought":
        bear_score += 1
        negatives.append("Stochastic overbought — short-term extension risk.")

    # ── 4. Volatility & bands ──
    bb_signal = bollinger.get("signal")
    bandwidth = bollinger.get("bandwidth")
    if bb_signal == "near_lower_band":
        bull_score += 1
        positives.append("Price near lower Bollinger band — mean-reversion bounce setup if trend intact.")
    elif bb_signal == "below_lower_band":
        bull_score += 1
        positives.append("Price below lower Bollinger band — sharp selloff, watch for capitulation reversal.")
    elif bb_signal in ("near_upper_band", "above_upper_band"):
        bear_score += 1
        negatives.append("Price at/above upper Bollinger band — extended; risk of pullback.")
    if bandwidth is not None and bandwidth < 0.08:
        highlights.append("Bollinger bandwidth is tight — volatility squeeze; breakout may follow.")

    atr_pct = atr.get("percentage")
    if atr_pct is not None:
        highlights.append(f"ATR volatility: {atr_pct:.1f}% of price — use for stop placement.")

    # ── 5. Volume & institutional flow proxy ──
    vol_ratio = volume.get("volume_ratio")
    vol_signal = volume.get("volume_signal")
    obv_trend = volume.get("obv_trend")
    if vol_signal == "high" and obv_trend == "rising":
        bull_score += 2
        positives.append(
            f"Volume {vol_ratio:.1f}x the 20-day average with rising OBV — institutional accumulation signature."
        )
    elif vol_signal == "high" and obv_trend == "falling":
        bear_score += 2
        negatives.append(
            f"Heavy volume ({vol_ratio:.1f}x avg) with falling OBV — distribution / institutional selling risk."
        )
    elif obv_trend == "rising":
        bull_score += 1
        positives.append("On-balance volume trending up — buyers absorbing supply.")
    elif obv_trend == "falling":
        bear_score += 1
        negatives.append("On-balance volume trending down — sellers in control.")

    # ── 6. Support / resistance & risk levels ──
    if sr and current_price:
        support = sr.get("support_1")
        resistance = sr.get("resistance_1")
        if support and current_price <= support * 1.02:
            positives.append(f"Price is testing support near ₹{support:.2f} — risk/reward favours buyers if it holds.")
            bull_score += 1
        if resistance and current_price >= resistance * 0.98:
            negatives.append(f"Price is pressing resistance near ₹{resistance:.2f} — breakout needs volume confirmation.")
            bear_score += 1
        if support and resistance:
            highlights.append(f"Key zone: support ₹{support:.2f} · resistance ₹{resistance:.2f}.")

    # ── 7. Candlestick patterns ──
    for pattern in patterns[:3]:
        label = pattern.get("pattern", "").replace("_", " ")
        signal = pattern.get("signal", "")
        if "bullish" in signal:
            bull_score += 1
            positives.append(f"{label.title()} pattern — bullish reversal signal.")
        elif "bearish" in signal:
            bear_score += 1
            negatives.append(f"{label.title()} pattern — bearish reversal signal.")

    # ── 8. VCP (included, not exclusive) ──
    vcp = detect_vcp(df)
    positives.extend(vcp.get("positives") or [])
    negatives.extend(vcp.get("negatives") or [])
    if vcp.get("detected"):
        bull_score += 2
        highlights.append("VCP-style contraction detected — breakout setup on volume would be high-conviction.")

    net = bull_score - bear_score
    if net >= 4:
        assessment = "bullish"
        bias = "Institutional technical bias: bullish"
    elif net <= -4:
        assessment = "bearish"
        bias = "Institutional technical bias: bearish"
    else:
        assessment = "neutral"
        bias = "Institutional technical bias: neutral / mixed"

    summary_parts = [bias]
    if highlights:
        summary_parts.append(highlights[0])
    if vcp.get("summary"):
        summary_parts.append(vcp["summary"])

    return {
        "title": "Institutional technical analysis",
        "assessment": assessment,
        "summary": " · ".join(summary_parts),
        "vcp_detected": bool(vcp.get("detected", False)),
        "technical_score": {
            "bullish": bull_score,
            "bearish": bear_score,
            "net": net,
        },
        "positives": _dedupe(positives)[:8],
        "negatives": _dedupe(negatives)[:8],
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip().lower()
        if item.strip() and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result
