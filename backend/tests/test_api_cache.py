import time
import unittest
from unittest.mock import patch

import requests

import data.indian_api as api


class DiskCachePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.key = api._cache_key("/historical_stats", {"stock_name": "CACHETEST", "stats": "ratios"})
        self.payload = {
            "data": {"ROE": {"Jun 2026": 18.0}},
            "provenance": {"provider": "IndianAPI", "status": "ok"},
        }
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        api._api_cache.pop(self.key, None)
        path = api._disk_cache_file(self.key)
        if path.exists():
            path.unlink()

    def test_cached_value_survives_process_restart(self):
        api._cache_set(self.key, self.payload, 600)
        api._api_cache.clear()  # emulate a fresh process with an empty memory cache

        self.assertEqual(api._cache_get(self.key), self.payload)

    def test_expired_entry_is_not_served_as_fresh(self):
        api._cache_set(self.key, self.payload, 600)
        stored = api._disk_cache_read(self.key)
        stored["ts"] = time.time() - 1200
        api._disk_cache_write(self.key, stored)
        api._api_cache.clear()

        self.assertIsNone(api._cache_get(self.key))

    def test_stale_cache_is_served_when_api_fails(self):
        api._cache_set(self.key, self.payload, 600)
        stored = api._disk_cache_read(self.key)
        stored["ts"] = time.time() - 7200
        api._disk_cache_write(self.key, stored)
        api._api_cache.clear()

        stale = api._stale_cache_result(self.key, {"http_status": 429})

        self.assertIsNotNone(stale)
        self.assertEqual(stale["data"], self.payload["data"])
        self.assertEqual(stale["provenance"]["status"], "stale_cache")
        self.assertTrue(stale["provenance"]["served_from_cache"])
        self.assertGreaterEqual(stale["provenance"]["cache_age_seconds"], 7200)

    def test_stale_cache_returns_none_without_prior_data(self):
        self.assertIsNone(api._stale_cache_result("/never-fetched", {"http_status": 429}))


class RateLimitFallbackTests(unittest.TestCase):
    def setUp(self):
        self.params = {"stock_name": "FALLBACK", "stats": "quarter_results"}
        self.key = api._cache_key("/historical_stats", self.params)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        api._api_cache.pop(self.key, None)
        path = api._disk_cache_file(self.key)
        if path.exists():
            path.unlink()

    @patch.dict("os.environ", {"INDIAN_API_KEY": "test-key"})
    @patch("data.indian_api.requests.get")
    def test_429_falls_back_to_cached_data(self, mock_get):
        api._cache_set(
            self.key,
            {"data": {"Sales": {"Jun 2026": 500}}, "provenance": {"status": "ok"}},
            0,  # already expired, so the request is attempted
        )
        api._api_cache.clear()

        error = requests.RequestException("429 Too Many Requests")
        error.response = type("R", (), {"status_code": 429})()
        mock_get.return_value.raise_for_status.side_effect = error

        result = api._get("/historical_stats", self.params)

        self.assertEqual(result["data"], {"Sales": {"Jun 2026": 500}})
        self.assertEqual(result["provenance"]["status"], "stale_cache")
        self.assertEqual(result["provenance"]["http_status"], 429)

    @patch.dict("os.environ", {"INDIAN_API_KEY": "test-key"})
    @patch("data.indian_api.requests.get")
    def test_429_without_cache_reports_error(self, mock_get):
        error = requests.RequestException("429 Too Many Requests")
        error.response = type("R", (), {"status_code": 429})()
        mock_get.return_value.raise_for_status.side_effect = error

        result = api._get("/historical_stats", {"stock_name": "NOCACHE", "stats": "ratios"})

        self.assertIsNone(result["data"])
        self.assertEqual(result["provenance"]["status"], "error")
        self.assertEqual(result["provenance"]["http_status"], 429)

    @patch.dict("os.environ", {"INDIAN_API_KEY": "test-key"})
    @patch("data.indian_api.requests.get")
    def test_429_starts_cooldown_skipping_further_calls(self, mock_get):
        api._rate_limited_until = 0.0
        error = requests.RequestException("429 Too Many Requests")
        error.response = type("R", (), {"status_code": 429})()
        mock_get.return_value.raise_for_status.side_effect = error

        first = api._get("/historical_stats", {"stock_name": "COOL1", "stats": "ratios"})
        second = api._get("/historical_stats", {"stock_name": "COOL2", "stats": "ratios"})

        self.assertEqual(first["provenance"]["http_status"], 429)
        self.assertEqual(second["provenance"]["http_status"], 429)
        self.assertEqual(mock_get.call_count, 1)
        self.assertIn("cooldown", second["provenance"]["error"].lower())
        api._rate_limited_until = 0.0


class SingleflightTests(unittest.TestCase):
    @patch.dict("os.environ", {"INDIAN_API_KEY": "test-key"})
    @patch("data.indian_api.requests.get")
    def test_parallel_gets_share_one_http_call(self, mock_get):
        import threading

        api._rate_limited_until = 0.0
        params = {"stock_name": "SINGLE", "stats": "ratios"}
        key = api._cache_key("/historical_stats", params)
        api._api_cache.pop(key, None)
        path = api._disk_cache_file(key)
        if path.exists():
            path.unlink()

        started = threading.Event()
        release = threading.Event()

        def slow_get(*_args, **_kwargs):
            started.set()
            release.wait(timeout=2)
            response = type("R", (), {})()
            response.raise_for_status = lambda: None
            response.json = lambda: {"ROE": 1}
            return response

        mock_get.side_effect = slow_get
        results = []

        def worker():
            results.append(api._get("/historical_stats", params))

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        self.assertTrue(started.wait(timeout=2))
        release.set()
        for t in threads:
            t.join(timeout=3)

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r["data"] == {"ROE": 1} for r in results))
        api._api_cache.pop(key, None)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    unittest.main()
