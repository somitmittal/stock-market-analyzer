import unittest
import uuid

from auth import register_user
from db import init_db
from portfolios import (
    add_holding,
    create_portfolio,
    list_portfolios_with_holdings,
)


class PortfolioOverviewTests(unittest.TestCase):
    def setUp(self):
        init_db()
        user = register_user(f"portfolio-test-{uuid.uuid4().hex[:8]}@example.com", "testpass123", "Tester")
        self.user_id = user["user"]["id"]

    def test_list_portfolios_with_holdings_returns_all_nested(self):
        first = create_portfolio(self.user_id, "Growth")
        second = create_portfolio(self.user_id, "Dividend")
        add_holding(self.user_id, first["id"], "RELIANCE", "NSE")
        add_holding(self.user_id, first["id"], "TCS", "NSE")
        add_holding(self.user_id, second["id"], "HDFCBANK", "NSE")

        overview = list_portfolios_with_holdings(self.user_id)
        by_name = {portfolio["name"]: portfolio for portfolio in overview}

        self.assertEqual(len(overview), 2)
        self.assertEqual(by_name["Growth"]["holding_count"], 2)
        self.assertEqual(by_name["Dividend"]["holding_count"], 1)
        self.assertEqual(
            sorted(holding["symbol"] for holding in by_name["Growth"]["holdings"]),
            ["RELIANCE", "TCS"],
        )


if __name__ == "__main__":
    unittest.main()
