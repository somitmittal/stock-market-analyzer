import unittest
from unittest.mock import patch

import pandas as pd

from data.fetcher import get_stock_data
from trading import get_quote, market_overview


class QuoteOptimizationTests(unittest.TestCase):
    def setUp(self):
        import trading

        trading._quote_cache.clear()
        trading._markets_cache["data"] = None
        trading._markets_cache["ts"] = 0.0

    @patch("data.fetcher.yfinance_enabled", return_value=True)
    @patch("data.fetcher._ohlcv_from_indian_api")
    @patch("data.fetcher._get_ticker")
    def test_short_period_prefers_yahoo_over_indian_api(
        self, mock_ticker, mock_indian, _yf_on
    ):
        frame = pd.DataFrame(
            {"Open": [10, 11], "High": [11, 12], "Low": [9, 10], "Close": [10.5, 11.5], "Volume": [1, 2]},
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )
        mock_ticker.return_value.history.return_value = frame

        df = get_stock_data("RELIANCE.NS", period="5d", interval="1d")

        self.assertEqual(len(df), 2)
        mock_indian.assert_not_called()
        mock_ticker.return_value.history.assert_called_once()

    @patch("trading.get_stock_data")
    def test_get_quote_uses_yahoo_first_short_lookback(self, mock_get):
        frame = pd.DataFrame(
            {"Close": [100.0, 105.0]},
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )
        mock_get.return_value = frame

        quote = get_quote("RELIANCE", "NSE")

        self.assertEqual(quote["ltp"], 105.0)
        self.assertAlmostEqual(quote["change_pct"], 5.0)
        mock_get.assert_called_once_with(
            "RELIANCE.NS", period="5d", interval="1d", prefer_yahoo=True
        )

    @patch("trading.get_quote")
    def test_market_overview_cached_second_call(self, mock_quote):
        mock_quote.return_value = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "ltp": 1.0,
            "change_pct": 0.0,
            "available": True,
        }

        first = market_overview()
        second = market_overview()

        self.assertEqual(first, second)
        # 8 seeds on first call only
        self.assertEqual(mock_quote.call_count, 8)


if __name__ == "__main__":
    unittest.main()
