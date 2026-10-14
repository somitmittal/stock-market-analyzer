import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import requests

import analysis.gemini_client as gemini_client
from analysis.llm_verdict import build_llm_verdict, _normalize_verdict


class LlmVerdictTests(unittest.TestCase):
    def _df(self) -> pd.DataFrame:
        dates = pd.date_range("2025-01-01", periods=60, freq="B")
        close = pd.Series(range(100, 160), index=dates, dtype=float)
        return pd.DataFrame(
            {
                "Open": close - 1,
                "High": close + 1,
                "Low": close - 2,
                "Close": close,
                "Volume": 1_000_000,
            }
        )

    def _research(self) -> dict:
        return {
            "company_profile": {"name": "Test Co", "industry": "Software & Programming"},
            "growth": {"available": True, "revenue_yoy_pct": 18, "profit_yoy_pct": 22},
            "valuation": {"available": True, "pe": 24, "peg": 1.1},
            "ownership": {"available": True, "promoter_holding_latest_pct": 50},
        }

    @patch("analysis.llm_verdict.is_configured", return_value=False)
    def test_falls_back_to_rules_without_gemini(self, _mock_configured):
        result = build_llm_verdict(
            symbol="TEST.NS",
            company_name="Test Co",
            current_price=150,
            df=self._df(),
            research=self._research(),
            news=[],
            technical={"trend": {"short": "uptrend", "medium": "uptrend", "long": "uptrend"}},
            fundamentals={"pe_ratio": 24},
            snapshot={"industry": "Software & Programming"},
        )
        self.assertEqual(result["analysis_source"], "rules")
        self.assertIn("quarterly_results", result["sections"])

    @patch("analysis.llm_verdict.generate_json")
    @patch("analysis.llm_verdict.is_configured", return_value=True)
    def test_uses_gemini_when_configured(self, _mock_configured, mock_generate):
        mock_generate.return_value = {
            "recommendation": "Buy",
            "confidence": "high",
            "rationale": "Test Co shows strong growth at a reasonable multiple.",
            "sections": {
                "business": {
                    "assessment": "strong",
                    "summary": "Leader in IT services.",
                    "positives": ["18% revenue growth"],
                    "negatives": ["Client concentration risk"],
                }
            },
        }
        result = build_llm_verdict(
            symbol="TEST.NS",
            company_name="Test Co",
            current_price=150,
            df=self._df(),
            research=self._research(),
            news=[{"title": "Test Co wins large deal"}],
            technical={"rsi": {"value": 58}},
            fundamentals={"pe_ratio": 24},
            snapshot={"industry": "Software & Programming"},
        )
        self.assertEqual(result["analysis_source"], "gemini")
        self.assertEqual(result["recommendation"], "Buy")
        self.assertEqual(result["sections"]["business"]["positives"][0], "18% revenue growth")

    def test_normalize_verdict_fills_missing_sections(self):
        fallback = {
            "recommendation": "Hold",
            "confidence": "medium",
            "rationale": "fallback",
            "sections": {
                "business": {
                    "title": "Business quality & visibility",
                    "assessment": "moderate",
                    "positives": ["fallback positive"],
                    "negatives": [],
                }
            },
        }
        normalized = _normalize_verdict(
            {"recommendation": "Buy", "confidence": "high", "rationale": "ai", "sections": {}},
            fallback,
        )
        self.assertEqual(normalized["recommendation"], "Buy")
        self.assertEqual(normalized["sections"]["business"]["positives"], ["fallback positive"])


class GeminiApiKeyTests(unittest.TestCase):
    def test_accepts_a_single_valid_key(self):
        key = "AIza" + "b" * 35
        with patch.dict("os.environ", {"GEMINI_API_KEY": key}):
            self.assertEqual(gemini_client._api_key(), key)

    def test_recovers_a_key_pasted_twice(self):
        key = "AIza" + "b" * 35
        with patch.dict("os.environ", {"GEMINI_API_KEY": key + key}):
            self.assertEqual(gemini_client._api_key(), key)

    def test_rejects_two_different_keys_concatenated(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "AIza" + "b" * 35 + "AIza" + "c" * 35}):
            self.assertIsNone(gemini_client._api_key())

    def test_rejects_missing_key(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            self.assertIsNone(gemini_client._api_key())


class GeminiRetryTests(unittest.TestCase):
    def _ok_response(self, text: str = '{"ok": true}') -> MagicMock:
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": text}]}}]
        }
        return response

    def setUp(self):
        patcher = patch.dict("os.environ", {"GEMINI_API_KEY": "AIza" + "b" * 35})
        patcher.start()
        self.addCleanup(patcher.stop)
        sleep_patcher = patch("analysis.gemini_client.time.sleep")
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    @patch("analysis.gemini_client.requests.post")
    def test_retries_transient_503_then_succeeds(self, mock_post):
        mock_post.side_effect = [
            MagicMock(status_code=503, text="overloaded"),
            self._ok_response(),
        ]

        self.assertEqual(gemini_client.generate_json("sys", "user"), {"ok": True})
        self.assertEqual(mock_post.call_count, 2)

    @patch("analysis.gemini_client.requests.post")
    def test_does_not_retry_client_error(self, mock_post):
        bad = MagicMock(status_code=400, text="invalid key")
        bad.raise_for_status.side_effect = requests.HTTPError("400 Bad Request")
        mock_post.return_value = bad

        with self.assertRaises(requests.HTTPError):
            gemini_client.generate_json("sys", "user")
        self.assertEqual(mock_post.call_count, 1)

    @patch("analysis.gemini_client.requests.post")
    def test_gives_up_after_max_attempts(self, mock_post):
        mock_post.return_value = MagicMock(status_code=503, text="overloaded")

        with self.assertRaises(requests.HTTPError):
            gemini_client.generate_json("sys", "user")
        self.assertEqual(mock_post.call_count, gemini_client.RETRY_ATTEMPTS)

    @patch("analysis.gemini_client.requests.post")
    def test_strips_markdown_fenced_json(self, mock_post):
        mock_post.return_value = self._ok_response('```json\n{"ok": true}\n```')

        self.assertEqual(gemini_client.generate_json("sys", "user"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
