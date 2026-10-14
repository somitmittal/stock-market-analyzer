import unittest
import uuid
from unittest.mock import patch

from auth import register_user
from db import init_db
from mutual_funds import buy_lumpsum, create_sip, list_funds, portfolio_summary
from trading import ensure_wallet, get_wallet, place_stock_order


class TradingAndFundsTests(unittest.TestCase):
    def setUp(self):
        init_db()
        user = register_user(
            f"nivesh-{uuid.uuid4().hex[:8]}@example.com",
            "testpass123",
            "Trader",
        )
        self.user_id = user["user"]["id"]

    def test_new_user_gets_paper_wallet(self):
        wallet = get_wallet(self.user_id)
        self.assertEqual(wallet["cash_balance"], 100_000.0)
        self.assertEqual(wallet["mode"], "paper")

    @patch("trading.get_quote")
    def test_buy_by_amount_like_kite(self, mock_quote):
        mock_quote.return_value = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "ltp": 1000.0,
            "change_pct": 1.2,
            "available": True,
        }
        order = place_stock_order(
            self.user_id,
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            amount=5000,
        )
        self.assertEqual(order["status"], "filled")
        self.assertEqual(order["quantity"], 5.0)
        wallet = get_wallet(self.user_id)
        self.assertEqual(wallet["cash_balance"], 95_000.0)

    def test_funds_catalog_supports_hundred_rupee_sip(self):
        catalog = list_funds(max_min_sip=100)
        self.assertGreaterEqual(catalog["count"], 1)
        self.assertTrue(all(f["min_sip"] <= 100 for f in catalog["funds"]))

    def test_create_sip_and_portfolio_summary(self):
        ensure_wallet(self.user_id)
        result = create_sip(self.user_id, "nifty50-index", 100, "monthly", invest_now=True)
        self.assertEqual(result["status"], "active")
        self.assertIsNotNone(result["first_installment"])
        summary = portfolio_summary(self.user_id)
        self.assertEqual(len(summary["sips"]), 1)
        self.assertGreater(summary["summary"]["mf_value"], 0)

    def test_lumpsum_rejects_below_minimum(self):
        with self.assertRaises(Exception):
            buy_lumpsum(self.user_id, "elss-tax", 100)


if __name__ == "__main__":
    unittest.main()
