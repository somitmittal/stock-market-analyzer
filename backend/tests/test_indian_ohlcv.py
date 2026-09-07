import unittest

from data.indian_api import history_to_ohlcv


class IndianOhlcvTests(unittest.TestCase):
    def test_builds_synthetic_ohlc_from_close_and_volume(self):
        history = {
            "datasets": [
                {
                    "metric": "Price",
                    "values": [
                        ["2026-01-01", "100"],
                        ["2026-01-02", "110"],
                        ["2026-01-03", "105"],
                    ],
                },
                {
                    "metric": "Volume",
                    "values": [
                        ["2026-01-01", 1000],
                        ["2026-01-02", 2000],
                        ["2026-01-03", 1500],
                    ],
                },
            ]
        }

        df = history_to_ohlcv(history, interval="1d")

        self.assertEqual(len(df), 3)
        self.assertEqual(df.iloc[0]["Open"], 100.0)
        self.assertEqual(df.iloc[1]["Open"], 100.0)
        self.assertEqual(df.iloc[1]["High"], 110.0)
        self.assertEqual(df.iloc[1]["Low"], 100.0)
        self.assertEqual(df.iloc[2]["Open"], 110.0)
        self.assertEqual(df.iloc[2]["Low"], 105.0)
        self.assertTrue(df.attrs["synthetic_ohlc"])
        self.assertEqual(df.attrs["ohlcv_provider"], "IndianAPI")

    def test_empty_history_returns_empty_frame(self):
        df = history_to_ohlcv({"datasets": []})
        self.assertTrue(df.empty)


if __name__ == "__main__":
    unittest.main()
