import unittest

from unittest.mock import patch

from analysis.research import analyze_company_research, merge_yahoo_fundamentals
from analysis.stock_analysis import assemble_research


class CompanyResearchTests(unittest.TestCase):
    def test_derives_growth_cash_quality_and_deterioration(self):
        quarterly = {
            "Sales": {
                "Jun 2025": 100,
                "Sep 2025": 110,
                "Dec 2025": 120,
                "Mar 2026": 130,
                "Jun 2026": 125,
            },
            "Net Profit": {
                "Jun 2025": 20,
                "Sep 2025": 22,
                "Dec 2025": 23,
                "Mar 2026": 24,
                "Jun 2026": 15,
            },
            "OPM %": {
                "Jun 2025": 20,
                "Sep 2025": 20,
                "Dec 2025": 20,
                "Mar 2026": 19,
                "Jun 2026": 16,
            },
        }
        cashflow = {
            "Cash from Operating Activity": {"Mar 2025": 18, "Mar 2026": 12},
            "Free Cash Flow": {"Mar 2025": 10, "Mar 2026": 4},
        }
        balance_sheet = {
            "Borrowings": {"Mar 2025": 50, "Mar 2026": 70},
            "Reserves": {"Mar 2025": 80, "Mar 2026": 90},
        }
        ratios = {
            "ROCE %": {"Mar 2025": 18, "Mar 2026": 16},
            "Cash Conversion Cycle": {"Mar 2025": 30, "Mar 2026": 40},
        }

        result = analyze_company_research(
            {"companyName": "Example", "industry": "Industrials"},
            {
                "quarter_results": quarterly,
                "cashflow": cashflow,
                "balancesheet": balance_sheet,
                "ratios": ratios,
                "shareholding_pattern_quarterly": {},
            },
        )

        self.assertAlmostEqual(result["growth"]["revenue_yoy_pct"], 25)
        self.assertAlmostEqual(result["growth"]["profit_yoy_pct"], -25)
        self.assertTrue(result["fundamental_deterioration"]["detected"])
        self.assertIn(
            "Borrowings are rising.",
            result["fundamental_deterioration"]["flags"],
        )
        self.assertEqual(
            result["management_efficiency"]["cash_conversion_cycle_trend"],
            "deteriorating",
        )

    def test_multibagger_scenarios_are_requirements_not_probabilities(self):
        result = analyze_company_research({}, {})
        scenarios = result["multibagger_scenarios"]

        self.assertEqual(len(scenarios), 4)
        self.assertTrue(all(item["probability"] is None for item in scenarios))
        two_x_three_year = next(
            item
            for item in scenarios
            if item["multiple"] == "2x" and item["years"] == 3
        )
        self.assertAlmostEqual(two_x_three_year["required_cagr_pct"], 25.99)

    def test_yahoo_fallback_fills_empty_research_pillars(self):
        empty = analyze_company_research({}, {})
        filled = merge_yahoo_fundamentals(
            empty,
            {
                "company_name": "Infosys Limited",
                "industry": "Software & Programming",
                "pe_ratio": 24.5,
                "pb_ratio": 7.1,
                "revenue_growth": 0.14,
                "earnings_growth": 0.12,
                "roe": 0.31,
                "free_cash_flow": 1.2e11,
                "operating_margin": 0.21,
                "52_week_high": 1900,
                "52_week_low": 1300,
            },
            {"available": True, "total_debt": 50_000, "total_equity": 80_000},
        )

        self.assertEqual(filled["fundamental_source"], "yahoo_finance")
        self.assertEqual(filled["company_profile"]["name"], "Infosys Limited")
        self.assertEqual(filled["company_profile"]["industry"], "Software & Programming")
        self.assertTrue(filled["growth"]["available"])
        self.assertAlmostEqual(filled["growth"]["revenue_yoy_pct"], 14)
        self.assertTrue(filled["valuation"]["available"])
        self.assertAlmostEqual(filled["valuation"]["pe"], 24.5)
        self.assertTrue(filled["cash_quality"]["available"])
        self.assertTrue(filled["balance_sheet"]["available"])
        self.assertGreaterEqual(filled["data_coverage"]["available_sections"], 4)

    def test_yahoo_fallback_does_not_overwrite_indian_api_data(self):
        research = analyze_company_research(
            {"companyName": "Example", "industry": "Industrials"},
            {
                "quarter_results": {
                    "Sales": {
                        "Jun 2025": 100,
                        "Sep 2025": 110,
                        "Dec 2025": 120,
                        "Mar 2026": 130,
                        "Jun 2026": 125,
                    },
                    "Net Profit": {
                        "Jun 2025": 20,
                        "Sep 2025": 22,
                        "Dec 2025": 23,
                        "Mar 2026": 24,
                        "Jun 2026": 25,
                    },
                },
                "cashflow": {},
                "balancesheet": {},
                "ratios": {},
                "shareholding_pattern_quarterly": {},
            },
        )
        filled = merge_yahoo_fundamentals(
            research,
            {"revenue_growth": 0.99, "company_name": "Yahoo Name", "pe_ratio": 8},
        )
        self.assertAlmostEqual(filled["growth"]["revenue_yoy_pct"], 25)
        self.assertEqual(filled["company_profile"]["name"], "Example")
        self.assertEqual(filled["valuation"]["pe"], 8)

    @patch("analysis.stock_analysis.analyze_sector_rotation")
    def test_assemble_research_uses_yahoo_when_indian_api_empty(self, mock_sector):
        mock_sector.return_value = {"available": False, "industry": "Information Technology Services"}
        inputs = {
            "indian_api": {"snapshot": None, "historical_stats": {}, "market_history": {}},
            "disclosures": {},
            "fundamentals": {
                "company_name": "Tata Consultancy Services",
                "industry": "Information Technology Services",
                "pe_ratio": 22,
                "revenue_growth": 0.08,
                "earnings_growth": 0.05,
                "52_week_high": 4500,
                "52_week_low": 3000,
            },
            "balance_sheet": {"available": False},
            "income_statement": {"available": False},
        }
        assembled = assemble_research("TCS.NS", inputs, "NSE")
        self.assertTrue(assembled["used_yahoo_fundamentals"])
        self.assertEqual(assembled["snapshot"]["companyName"], "Tata Consultancy Services")
        self.assertTrue(assembled["research"]["valuation"]["available"])


if __name__ == "__main__":
    unittest.main()
