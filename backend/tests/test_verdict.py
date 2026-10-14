import unittest

import pandas as pd

from analysis.verdict import build_investment_verdict


class VerdictTests(unittest.TestCase):
    def _sample_research(self) -> dict:
        return {
            "company_profile": {
                "industry": "Information Technology Services",
                "description": "Software exporter to US clients",
            },
            "growth": {
                "available": True,
                "revenue_yoy_pct": 28,
                "profit_yoy_pct": 30,
                "operating_margin_yoy_change_pp": 1.5,
                "latest_period": "Jun 2026",
            },
            "cash_quality": {
                "available": True,
                "operating_cash_flow_latest": 100,
                "free_cash_flow_latest": 50,
                "cash_profit_conversion": 0.9,
            },
            "balance_sheet": {
                "available": True,
                "borrowings_trend": "falling",
                "reserves_trend": "rising",
            },
            "ownership": {
                "available": True,
                "promoter_holding_latest_pct": 55,
                "promoter_holding_trend": "rising",
                "fii_holding_latest_pct": 12,
                "dii_holding_latest_pct": 10,
                "pledging": {"available": False},
            },
            "moat_evidence": {
                "available": True,
                "evidence": ["Five-year average ROE: 18.00%"],
            },
            "sector_context": {
                "available": True,
                "status": "leading",
                "relative_strength_pct": 4.5,
            },
            "order_book": {"available": False},
            "management_guidance": {"available": False},
            "recent_disclosures": {"categories": {}},
        }

    def _sample_df(self) -> pd.DataFrame:
        dates = pd.date_range("2025-01-01", periods=120, freq="B")
        close = pd.Series(range(100, 220), index=dates, dtype=float)
        return pd.DataFrame(
            {
                "Open": close - 1,
                "High": close + 2,
                "Low": close - 2,
                "Close": close,
                "Volume": pd.Series([1_000_000 + i * 1000 for i in range(len(dates))], index=dates),
            }
        )

    def test_builds_buy_verdict_for_strong_company(self):
        research = self._sample_research()
        historical_stats = {
            "quarter_results": {
                "Sales": {"Mar 2026": 100, "Jun 2026": 130},
                "Net Profit": {"Mar 2026": 20, "Jun 2026": 28},
            },
            "shareholding_pattern_quarterly": {
                "FIIs": {"Mar 2026": 10, "Jun 2026": 12},
                "DIIs": {"Mar 2026": 8, "Jun 2026": 10},
            },
        }
        result = build_investment_verdict(
            self._sample_df(),
            research,
            [{"title": "Company reports record growth and strong demand"}],
            {"trend": {"direction": "uptrend"}, "rsi": {"value": 55}},
            historical_stats=historical_stats,
        )

        self.assertIn(result["recommendation"], ("Buy", "Hold"))
        self.assertIn("business", result["sections"])
        self.assertIn("quarterly_results", result["sections"])
        self.assertEqual(result["sections"]["quarterly_results"]["assessment"], "phenomenal")

    def test_flags_weak_quarterly_results(self):
        research = self._sample_research()
        research["growth"] = {
            "available": True,
            "revenue_yoy_pct": 5,
            "profit_yoy_pct": -3,
            "operating_margin_yoy_change_pp": -2,
            "latest_period": "Jun 2026",
        }
        historical_stats = {
            "quarter_results": {
                "Sales": {"Mar 2026": 100, "Jun 2026": 102},
                "Net Profit": {"Mar 2026": 20, "Jun 2026": 18},
            },
        }
        result = build_investment_verdict(
            self._sample_df(),
            research,
            [],
            None,
            historical_stats=historical_stats,
        )
        self.assertIn(result["sections"]["quarterly_results"]["assessment"], ("weak", "ok"))


if __name__ == "__main__":
    unittest.main()
