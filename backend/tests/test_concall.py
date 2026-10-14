import unittest

from analysis.concall import _rank_sentences, summarize_concall_document


class ConcallSummaryTests(unittest.TestCase):
    def test_ranks_positive_sentences(self):
        sentences = [
            "Revenue growth remained strong with robust demand.",
            "The office is located in Mumbai.",
            "Margins improved due to cost discipline.",
        ]
        positives = _rank_sentences(sentences, ("growth", "strong", "robust", "improved"))
        self.assertTrue(any("growth" in item.lower() for item in positives))

    def test_unavailable_when_no_text(self):
        result = summarize_concall_document("https://example.test/missing.pdf", "Q1 call")
        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()
