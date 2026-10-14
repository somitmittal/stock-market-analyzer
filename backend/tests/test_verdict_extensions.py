import unittest

import pandas as pd

from analysis.institutional_technical import analyze_institutional_technicals
from analysis.verdict import _analyze_price_action, _analyze_valuation, build_investment_verdict


class VerdictExtensionTests(unittest.TestCase):
    def _research(self) -> dict:
        return {
            "company_profile": {"industry": "Information Technology Services"},
            "growth": {
                "available": True,
                "revenue_yoy_pct": 28,
                "profit_yoy_pct": 30,
                "operating_margin_yoy_change_pp": 1.0,
            },
            "valuation": {
                "available": True,
                "pe": 30,
                "price_to_book": 8,
                "peg": 1.1,
                "eps_growth_pct": 28,
            },
            "fundamental_deterioration": {"detected": False, "flags": []},
            "management_guidance": {"available": False},
            "recent_disclosures": {"categories": {}},
        }

    def _df(self) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=260, freq="B")
        values = [100 + i * 0.05 for i in range(len(dates))]
        close = pd.Series(values, index=dates, dtype=float)
        return pd.DataFrame(
            {
                "Open": close - 0.5,
                "High": close + 1,
                "Low": close - 1,
                "Close": close,
                "Volume": 1_000_000,
            }
        )

    def test_valuation_flags_peer_comparison(self):
        section = _analyze_valuation(self._research(), {}, 3000)
        self.assertIn("valuation", section["title"].lower())
        self.assertTrue(section["positives"] or section["negatives"])

    def test_price_action_flags_trim_near_highs(self):
        df = self._df()
        snapshot = {"yearHigh": float(df["Close"].iloc[-1]) * 0.99, "yearLow": 80}
        section = _analyze_price_action(df, self._research(), float(df["Close"].iloc[-1]), snapshot)
        self.assertTrue(any("profit" in item.lower() or "high" in item.lower() for item in section["negatives"]))

    def test_institutional_technicals_use_full_indicator_stack(self):
        technical = {
            "trend": {"short": "uptrend", "medium": "uptrend", "long": "uptrend"},
            "moving_averages": {
                "overall": "strong_bullish",
                "cross": "none",
                "sma": {"200": {"value": 2800, "signal": "bullish"}},
            },
            "rsi": {"value": 58, "signal": "neutral", "divergence": "none"},
            "macd": {"crossover": "bullish", "trend": "bullish"},
            "adx": {"adx": 28, "trend_strength": "strong", "direction": "bullish"},
            "bollinger": {"signal": "neutral", "bandwidth": 0.12},
            "volume_analysis": {"volume_ratio": 1.8, "volume_signal": "high", "obv_trend": "rising"},
            "support_resistance": {"support_1": 2950, "resistance_1": 3100},
            "atr": {"percentage": 2.1},
            "stochastic": {"signal": "neutral"},
            "candlestick_patterns": [],
        }
        section = analyze_institutional_technicals(self._df(), technical)
        self.assertEqual(section["title"], "Institutional technical analysis")
        self.assertIn(section["assessment"], ("bullish", "neutral"))
        self.assertTrue(any("ADX" in item for item in section["positives"]))
        self.assertTrue(any("OBV" in item or "Volume" in item for item in section["positives"]))

    def test_build_investment_verdict_includes_new_sections(self):
        result = build_investment_verdict(
            self._df(),
            self._research(),
            [],
            {"trend": {"direction": "uptrend"}, "rsi": {"value": 55}},
            historical_stats={},
            current_price=3000,
            snapshot={"yearHigh": 3100, "yearLow": 2200},
        )
        self.assertIn("valuation", result["sections"])
        self.assertIn("price_action", result["sections"])


if __name__ == "__main__":
    unittest.main()
