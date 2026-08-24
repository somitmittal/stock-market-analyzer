import unittest

from analysis.research import analyze_company_research


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


if __name__ == "__main__":
    unittest.main()
