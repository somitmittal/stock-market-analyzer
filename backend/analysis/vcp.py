"""Volatility Contraction Pattern (VCP) detection for breakout setups."""

from __future__ import annotations

import pandas as pd
import ta


def detect_vcp(df: pd.DataFrame) -> dict:
    """Detect a simplified VCP: contracting ranges, falling volatility, volume pickup."""
    if df is None or len(df) < 80:
        return {
            "available": False,
            "detected": False,
            "summary": "Insufficient price history for VCP analysis.",
        }

    work = df.tail(min(len(df), 180)).copy()
    close = work["Close"]
    high = work["High"]
    low = work["Low"]
    volume = work["Volume"]

    atr = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()
    atr_recent = float(atr.iloc[-1]) if not atr.empty else None
    atr_mid = float(atr.iloc[-30]) if len(atr) >= 30 else None
    atr_old = float(atr.iloc[-60]) if len(atr) >= 60 else None
    volatility_contracting = (
        atr_recent is not None
        and atr_mid is not None
        and atr_old is not None
        and atr_recent < atr_mid < atr_old
    )

    range_pct = (high.rolling(15).max() - low.rolling(15).min()) / close
    recent_ranges = range_pct.dropna().tail(45)
    range_contracting = False
    if len(recent_ranges) >= 30:
        first_third = recent_ranges.iloc[:15].mean()
        last_third = recent_ranges.iloc[-15:].mean()
        range_contracting = last_third < first_third * 0.85

    vol_avg = volume.rolling(20).mean()
    recent_up_volume = volume[close.diff() > 0].tail(5).mean()
    volume_strength = (
        recent_up_volume is not None
        and not pd.isna(recent_up_volume)
        and vol_avg.iloc[-1] not in (None, 0)
        and not pd.isna(vol_avg.iloc[-1])
        and recent_up_volume > float(vol_avg.iloc[-1]) * 1.15
    )

    year_high = float(close.tail(252).max()) if len(close) >= 60 else float(close.max())
    near_high = float(close.iloc[-1]) >= year_high * 0.8

    above_ma50 = False
    ma50 = close.rolling(50).mean()
    if len(ma50.dropna()) >= 1:
        above_ma50 = float(close.iloc[-1]) > float(ma50.iloc[-1])

    score = sum(
        [
            volatility_contracting,
            range_contracting,
            volume_strength,
            near_high,
            above_ma50,
        ]
    )
    detected = bool(score >= 3 and (volatility_contracting or range_contracting))

    positives = []
    negatives = []
    if volatility_contracting:
        positives.append("Volatility is contracting — classic VCP base building.")
    if range_contracting:
        positives.append("Recent trading range is tightening versus earlier consolidation.")
    if volume_strength:
        positives.append("Up-days are showing stronger volume — possible accumulation.")
    if near_high and above_ma50:
        positives.append("Price is holding near highs above the 50-day average.")
    if not volatility_contracting and not range_contracting:
        negatives.append("No clear volatility contraction yet.")
    if not volume_strength:
        negatives.append("Volume has not clearly expanded on up-days.")
    if not above_ma50:
        negatives.append("Price is still below the 50-day moving average.")

    if detected:
        summary = (
            "VCP-style setup detected: tightening price action with supportive volume. "
            "A breakout on strong volume would be constructive."
        )
    elif score >= 2:
        summary = (
            "Early-stage consolidation with some VCP traits, but not a fully formed pattern yet."
        )
    else:
        summary = "No meaningful VCP setup visible on the current chart."

    return {
        "available": True,
        "detected": detected,
        "score": int(score),
        "signals": {
            "volatility_contracting": bool(volatility_contracting),
            "range_contracting": bool(range_contracting),
            "volume_strength": bool(volume_strength),
            "near_high": bool(near_high),
            "above_ma50": bool(above_ma50),
        },
        "summary": summary,
        "positives": positives,
        "negatives": negatives,
    }
