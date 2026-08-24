import unittest

from analysis.research import analyze_company_research
from analysis.sector_rotation import _classify, _resolve_sector
from data.disclosures import _matching_sentences, _normalize_announcement


class DisclosureClassificationTests(unittest.TestCase):
    def test_classifies_order_and_concall_filings_with_official_attachment(self):
        record = _normalize_announcement(
            {
                "NEWSID": "filing-1",
                "NEWS_DT": "2026-08-01T10:00:00",
                "NEWSSUB": "Investor call transcript and new order received",
                "ATTACHMENTNAME": "filing.pdf",
            }
        )

        self.assertIn("concall", record["categories"])
        self.assertIn("order_book", record["categories"])
        self.assertEqual(
            record["attachment_url"],
            "https://www.bseindia.com/xml-data/corpfiling/AttachLive/filing.pdf",
        )

    def test_extracts_only_sentences_with_requested_evidence(self):
        text = (
            "Revenue increased during the quarter. "
            "The order book stands at Rs 500 crore. "
            "Employee costs were stable."
        )

        self.assertEqual(
            _matching_sentences(text, ("order book",)),
            ["The order book stands at Rs 500 crore."],
        )

    def test_research_exposes_filing_evidence(self):
        pledge = {
            "available": True,
            "excerpts": ["No promoter shares are pledged."],
            "source": {"attachment_url": "https://example.test/filing.pdf"},
        }
        result = analyze_company_research(
            {},
            {},
            disclosures={
                "available": True,
                "analysis": {"promoter_pledging": pledge},
                "categories": {},
            },
        )

        self.assertTrue(result["ownership"]["pledging"]["available"])
        self.assertEqual(
            result["ownership"]["pledging"]["excerpts"],
            ["No promoter shares are pledged."],
        )


class SectorRotationTests(unittest.TestCase):
    def test_maps_reported_industry_to_nse_sector(self):
        self.assertEqual(_resolve_sector("Information Technology Services"), "it")
        self.assertEqual(_resolve_sector("Renewable Power Producer"), "energy")

    def test_classifies_absolute_and_relative_performance(self):
        self.assertEqual(_classify(8, 3), "leading")
        self.assertEqual(_classify(-2, 1), "improving_relative")
        self.assertEqual(_classify(2, -1), "weakening_relative")
        self.assertEqual(_classify(-2, -1), "lagging")


if __name__ == "__main__":
    unittest.main()
