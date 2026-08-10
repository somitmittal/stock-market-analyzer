"""
Technical analysis engine.
Computes RSI, MACD, Bollinger Bands, moving averages, Stochastic, ADX,
volume analysis, support/resistance, and candlestick patterns.
"""
import pandas as pd
import numpy as np
import ta


def compute_all_indicators(df: pd.DataFrame) -> dict:
    """Compute all technical indicators and return a structured result."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    indicators = {}
    indicators["rsi"] = compute_rsi(close)
    indicators["macd"] = compute_macd(close)
    indicators["bollinger"] = compute_bollinger(close)
    indicators["moving_averages"] = compute_moving_averages(close)
    indicators["stochastic"] = compute_stochastic(high, low, close)
    indicators["adx"] = compute_adx(high, low, close)
    indicators["atr"] = compute_atr(high, low, close)
    indicators["volume_analysis"] = compute_volume_analysis(close, volume)
    indicators["support_resistance"] = compute_support_resistance(df)
    indicators["candlestick_patterns"] = detect_candlestick_patterns(df)
    indicators["trend"] = determine_trend(close)

    return indicators


def compute_rsi(close: pd.Series, window: int = 14) -> dict:
    rsi_indicator = ta.momentum.RSIIndicator(close, window=window)
    rsi_values = rsi_indicator.rsi()
    current_rsi = float(rsi_values.iloc[-1]) if not rsi_values.empty else None

    signal = "neutral"
    if current_rsi is not None:
        if current_rsi < 30:
            signal = "oversold"
        elif current_rsi < 40:
            signal = "approaching_oversold"
        elif current_rsi > 70:
            signal = "overbought"
        elif current_rsi > 60:
            signal = "approaching_overbought"

    divergence = _detect_rsi_divergence(close, rsi_values)

    return {
        "value": round(current_rsi, 2) if current_rsi else None,
        "signal": signal,
        "divergence": divergence,
        "history": _series_tail(rsi_values, 30),
    }


def compute_macd(close: pd.Series) -> dict:
    macd_ind = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_line = macd_ind.macd()
    signal_line = macd_ind.macd_signal()
    histogram = macd_ind.macd_diff()

    current_macd = _safe_last(macd_line)
    current_signal = _safe_last(signal_line)
    current_hist = _safe_last(histogram)

    crossover = "none"
    if len(histogram) >= 2:
        prev_hist = _safe_val(histogram, -2)
        if prev_hist is not None and current_hist is not None:
            if prev_hist < 0 and current_hist > 0:
                crossover = "bullish"
            elif prev_hist > 0 and current_hist < 0:
                crossover = "bearish"

    return {
        "macd": round(current_macd, 4) if current_macd else None,
        "signal": round(current_signal, 4) if current_signal else None,
        "histogram": round(current_hist, 4) if current_hist else None,
        "crossover": crossover,
        "trend": "bullish" if (current_macd and current_signal and current_macd > current_signal) else "bearish",
    }


def compute_bollinger(close: pd.Series, window: int = 20, std_dev: int = 2) -> dict:
    bb = ta.volatility.BollingerBands(close, window=window, window_dev=std_dev)
    upper = _safe_last(bb.bollinger_hband())
    middle = _safe_last(bb.bollinger_mavg())
    lower = _safe_last(bb.bollinger_lband())
    current_price = float(close.iloc[-1])

    pct_b = _safe_last(bb.bollinger_pband())
    bandwidth = _safe_last(bb.bollinger_wband())

    signal = "neutral"
    if pct_b is not None:
        if pct_b < 0:
            signal = "below_lower_band"
        elif pct_b < 0.2:
            signal = "near_lower_band"
        elif pct_b > 1:
            signal = "above_upper_band"
        elif pct_b > 0.8:
            signal = "near_upper_band"

    return {
        "upper": round(upper, 2) if upper else None,
        "middle": round(middle, 2) if middle else None,
        "lower": round(lower, 2) if lower else None,
        "pct_b": round(pct_b, 4) if pct_b else None,
        "bandwidth": round(bandwidth, 4) if bandwidth else None,
        "signal": signal,
    }


def compute_moving_averages(close: pd.Series) -> dict:
    current_price = float(close.iloc[-1])
    periods = [9, 20, 50, 100, 200]
    result = {"current_price": round(current_price, 2), "sma": {}, "ema": {}}

    for p in periods:
        if len(close) >= p:
            sma_val = float(close.rolling(window=p).mean().iloc[-1])
            ema_val = float(close.ewm(span=p, adjust=False).mean().iloc[-1])
            result["sma"][str(p)] = {
                "value": round(sma_val, 2),
                "signal": "bullish" if current_price > sma_val else "bearish",
            }
            result["ema"][str(p)] = {
                "value": round(ema_val, 2),
                "signal": "bullish" if current_price > ema_val else "bearish",
            }

    bullish_count = sum(1 for v in result["sma"].values() if v["signal"] == "bullish")
    total = len(result["sma"])
    result["overall"] = "strong_bullish" if bullish_count == total else \
                        "bullish" if bullish_count > total / 2 else \
                        "bearish" if bullish_count < total / 2 else "neutral"

    _detect_golden_death_cross(close, result)
    return result


def compute_stochastic(high: pd.Series, low: pd.Series, close: pd.Series) -> dict:
    stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
    k = _safe_last(stoch.stoch())
    d = _safe_last(stoch.stoch_signal())

    signal = "neutral"
    if k is not None:
        if k < 20:
            signal = "oversold"
        elif k > 80:
            signal = "overbought"

    return {
        "k": round(k, 2) if k else None,
        "d": round(d, 2) if d else None,
        "signal": signal,
    }


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series) -> dict:
    adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
    adx_val = _safe_last(adx_ind.adx())
    plus_di = _safe_last(adx_ind.adx_pos())
    minus_di = _safe_last(adx_ind.adx_neg())

    trend_strength = "no_trend"
    if adx_val is not None:
        if adx_val > 50:
            trend_strength = "very_strong"
        elif adx_val > 25:
            trend_strength = "strong"
        elif adx_val > 20:
            trend_strength = "weak"

    direction = "neutral"
    if plus_di is not None and minus_di is not None:
        direction = "bullish" if plus_di > minus_di else "bearish"

    return {
        "adx": round(adx_val, 2) if adx_val else None,
        "plus_di": round(plus_di, 2) if plus_di else None,
        "minus_di": round(minus_di, 2) if minus_di else None,
        "trend_strength": trend_strength,
        "direction": direction,
    }


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series) -> dict:
    atr_ind = ta.volatility.AverageTrueRange(high, low, close, window=14)
    atr_val = _safe_last(atr_ind.average_true_range())
    current_price = float(close.iloc[-1])
    atr_pct = (atr_val / current_price * 100) if atr_val and current_price else None

    return {
        "value": round(atr_val, 2) if atr_val else None,
        "percentage": round(atr_pct, 2) if atr_pct else None,
    }


def compute_volume_analysis(close: pd.Series, volume: pd.Series) -> dict:
    current_vol = float(volume.iloc[-1])
    avg_vol_20 = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else current_vol
    vol_ratio = current_vol / avg_vol_20 if avg_vol_20 > 0 else 1

    obv = ta.volume.OnBalanceVolumeIndicator(close, volume)
    obv_values = obv.on_balance_volume()
    obv_trend = "rising" if len(obv_values) >= 5 and float(obv_values.iloc[-1]) > float(obv_values.iloc[-5]) else "falling"

    return {
        "current_volume": int(current_vol),
        "avg_volume_20d": int(avg_vol_20),
        "volume_ratio": round(vol_ratio, 2),
        "volume_signal": "high" if vol_ratio > 1.5 else "low" if vol_ratio < 0.5 else "normal",
        "obv_trend": obv_trend,
    }


def compute_support_resistance(df: pd.DataFrame, lookback: int = 60) -> dict:
    recent = df.tail(lookback)
    close = recent["Close"]
    high = recent["High"]
    low = recent["Low"]
    current_price = float(close.iloc[-1])

    pivot = (float(high.iloc[-1]) + float(low.iloc[-1]) + current_price) / 3
    r1 = 2 * pivot - float(low.iloc[-1])
    s1 = 2 * pivot - float(high.iloc[-1])
    r2 = pivot + (float(high.iloc[-1]) - float(low.iloc[-1]))
    s2 = pivot - (float(high.iloc[-1]) - float(low.iloc[-1]))

    recent_highs = sorted(high.nlargest(5).unique().tolist(), reverse=True)
    recent_lows = sorted(low.nsmallest(5).unique().tolist())

    return {
        "pivot": round(pivot, 2),
        "resistance_1": round(r1, 2),
        "resistance_2": round(r2, 2),
        "support_1": round(s1, 2),
        "support_2": round(s2, 2),
        "recent_highs": [round(h, 2) for h in recent_highs[:3]],
        "recent_lows": [round(l, 2) for l in recent_lows[:3]],
    }


def detect_candlestick_patterns(df: pd.DataFrame) -> list[dict]:
    if len(df) < 3:
        return []

    patterns = []
    o, h, l, c = df["Open"].iloc[-1], df["High"].iloc[-1], df["Low"].iloc[-1], df["Close"].iloc[-1]
    po, pc = df["Open"].iloc[-2], df["Close"].iloc[-2]
    body = abs(c - o)
    total_range = h - l if h != l else 0.001
    body_pct = body / total_range

    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l

    if body_pct < 0.1:
        patterns.append({"pattern": "doji", "signal": "reversal", "strength": "moderate"})
    if lower_shadow > 2 * body and upper_shadow < body * 0.3 and c > o:
        patterns.append({"pattern": "hammer", "signal": "bullish_reversal", "strength": "strong"})
    if upper_shadow > 2 * body and lower_shadow < body * 0.3 and o > c:
        patterns.append({"pattern": "shooting_star", "signal": "bearish_reversal", "strength": "strong"})
    if pc < po and c > o and c > po and o < pc:
        patterns.append({"pattern": "bullish_engulfing", "signal": "bullish_reversal", "strength": "strong"})
    if pc > po and o > c and o > pc and c < po:
        patterns.append({"pattern": "bearish_engulfing", "signal": "bearish_reversal", "strength": "strong"})

    return patterns


def determine_trend(close: pd.Series) -> dict:
    if len(close) < 50:
        return {"short": "insufficient_data", "medium": "insufficient_data", "long": "insufficient_data"}

    short_sma = float(close.rolling(10).mean().iloc[-1])
    medium_sma = float(close.rolling(30).mean().iloc[-1])
    current = float(close.iloc[-1])

    short_trend = "uptrend" if current > short_sma else "downtrend"

    if len(close) >= 100:
        long_sma = float(close.rolling(50).mean().iloc[-1])
        medium_trend = "uptrend" if short_sma > medium_sma else "downtrend"
        long_trend = "uptrend" if medium_sma > long_sma else "downtrend"
    else:
        medium_trend = "uptrend" if current > medium_sma else "downtrend"
        long_trend = "insufficient_data"

    return {"short": short_trend, "medium": medium_trend, "long": long_trend}


def _detect_rsi_divergence(close: pd.Series, rsi: pd.Series) -> str:
    if len(close) < 20 or len(rsi) < 20:
        return "none"
    price_trend = float(close.iloc[-1]) - float(close.iloc[-10])
    rsi_trend = float(rsi.iloc[-1]) - float(rsi.iloc[-10]) if not rsi.iloc[-10:].isna().all() else 0

    if price_trend < 0 and rsi_trend > 0:
        return "bullish_divergence"
    elif price_trend > 0 and rsi_trend < 0:
        return "bearish_divergence"
    return "none"


def _detect_golden_death_cross(close: pd.Series, result: dict):
    if len(close) < 200:
        result["cross"] = "insufficient_data"
        return
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    if len(sma50) >= 2 and len(sma200) >= 2:
        prev_diff = float(sma50.iloc[-2]) - float(sma200.iloc[-2])
        curr_diff = float(sma50.iloc[-1]) - float(sma200.iloc[-1])
        if prev_diff < 0 and curr_diff > 0:
            result["cross"] = "golden_cross"
        elif prev_diff > 0 and curr_diff < 0:
            result["cross"] = "death_cross"
        else:
            result["cross"] = "none"


def _safe_last(series: pd.Series):
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    return float(val) if not pd.isna(val) else None


def _safe_val(series: pd.Series, idx: int):
    try:
        val = series.iloc[idx]
        return float(val) if not pd.isna(val) else None
    except (IndexError, KeyError):
        return None


def _series_tail(series: pd.Series, n: int) -> list:
    return [round(float(v), 2) for v in series.tail(n).dropna().tolist()]
