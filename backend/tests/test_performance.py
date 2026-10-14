import unittest
from unittest.mock import patch

from data.disclosures import fetch_recent_disclosures
from data.indian_api import fundamentals_from_snapshot


class PerformanceOptimizationsTests(unittest.TestCase):
    def test_fundamentals_from_snapshot_maps_valuation_metrics(self):
        snapshot = {
            "companyName": "Example Ltd",
            "industry": "Oil & Gas",
            "yearHigh": 1500,
            "yearLow": 1100,
            "keyMetrics": {
                "valuation": [
                    {
                        "key": "pPerEBasicExcludingExtraordinaryItemsTTM",
                        "value": "23.4",
                    },
                    {
                        "key": "priceToBookMostRecentFiscalYear",
                        "value": "1.9",
                    },
                ],
                "priceandVolume": [{"key": "marketCap", "value": "1000000"}],
            },
        }

        fundamentals = fundamentals_from_snapshot(snapshot, "EXAMPLE.NS")

        self.assertEqual(fundamentals["company_name"], "Example Ltd")
        self.assertEqual(fundamentals["industry"], "Oil & Gas")
        self.assertEqual(fundamentals["pe_ratio"], 23.4)
        self.assertEqual(fundamentals["pb_ratio"], 1.9)
        self.assertEqual(fundamentals["market_cap"], 1000000.0)
        self.assertEqual(fundamentals["52_week_high"], 1500.0)

    @patch("data.disclosures._extract_pdf_text")
    @patch("data.disclosures.BSE")
    def test_fast_disclosures_skip_pdf_extraction(self, mock_bse, mock_extract_pdf):
        mock_client = mock_bse.return_value.__enter__.return_value
        mock_client.getScripCode.return_value = "500325"
        mock_client.announcements.return_value = {
            "Table": [
                {
                    "NEWSID": "1",
                    "NEWS_DT": "2026-08-01T10:00:00",
                    "NEWSSUB": "Investor presentation",
                    "ATTACHMENTNAME": "filing.pdf",
                }
            ],
            "Table1": [{"ROWCNT": 1}],
        }

        result = fetch_recent_disclosures("RELIANCE", extract_evidence=False)

        self.assertTrue(result["available"])
        self.assertEqual(
            result["provenance"]["evidence_extraction"],
            "metadata_only",
        )
        mock_extract_pdf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
