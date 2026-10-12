"""覆盖行情错价、过期行情和上市历史不足的回归测试。"""

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from us_stock_agent.market_data import YFinanceProvider
from us_stock_agent.models import Holding, Portfolio, MarketSnapshot
from us_stock_agent.portfolio import build_portfolio_view, load_portfolio_from_dict
from us_stock_agent.decision import score_position


def sample_frame():
    """构造与最新 SPCX 公开数据同口径的小样本。"""
    return pd.DataFrame({"Open": [161., 165.34], "High": [168., 166.38],
                         "Low": [160., 160.61], "Close": [160.57, 162.57],
                         "Volume": [100, 200], "Stock Splits": [0., 0.]},
                        index=pd.date_range("2026-10-08", periods=2, name="Date", tz="America/New_York"))


class TestMarketIntegrity(unittest.TestCase):
    """错误的快照、币种和样本长度必须能被检测。"""

    def provider(self, *, frame=None, metadata=None):
        """注入真实接口形状的离线 Yahoo 响应。"""
        ticker = SimpleNamespace(fast_info={"last_price": 27., "previous_close": 26.},
                                 history=lambda **kwargs: sample_frame() if frame is None else frame,
                                 history_metadata=metadata or {"symbol": "SPCX", "currency": "USD", "longName": "Space Exploration Technologies Corp."})
        provider = YFinanceProvider.__new__(YFinanceProvider)
        provider.yf = SimpleNamespace(Ticker=lambda symbol: ticker, download=lambda *args, **kwargs: sample_frame())
        return provider

    def test_snapshot_uses_dated_regular_close_instead_of_fast_info(self):
        """旧 fast_info 不得覆盖本次日线收盘价。"""
        with patch("us_stock_agent.market_data.datetime", create=True) as clock:
            clock.now.return_value = datetime(2026, 10, 12, 4, tzinfo=timezone.utc)
            quote = self.provider().fetch_snapshot(["SPCX"])["SPCX"]
        self.assertAlmostEqual(quote.price, 162.57)
        self.assertEqual(quote.data_time[:10], "2026-10-09")
        self.assertEqual(quote.name, "Space Exploration Technologies Corp.")

    def test_rejects_stale_delisted_history(self):
        """退市旧价格必须报错，不得继续计算持仓净值。"""
        frame = sample_frame()
        frame.index = pd.date_range("2020-01-01", periods=2, name="Date", tz="America/New_York")
        with self.assertRaisesRegex(ValueError, "过期|交易日"):
            self.provider(frame=frame).fetch_snapshot(["SPCX"])

    def test_rejects_nonfinite_price(self):
        """NaN 行情不得进入盈亏计算。"""
        portfolio = Portfolio(currency="USD", cash=0, holdings=[Holding("SPCX", 1)])
        with self.assertRaisesRegex(ValueError, "行情|价格"):
            build_portfolio_view(portfolio, {"SPCX": MarketSnapshot("SPCX", float("nan"))})

    def test_rejects_currency_mismatch(self):
        """未提供汇率时不能把不同币种直接相加。"""
        portfolio = Portfolio(currency="USD", cash=0, holdings=[Holding("SPCX", 1)])
        with self.assertRaisesRegex(ValueError, "币种"):
            build_portfolio_view(portfolio, {"SPCX": MarketSnapshot("SPCX", 100, currency="EUR")})

    def test_duplicate_symbols_are_rejected(self):
        """重复代码会造成不同股数或成本的持仓被覆盖。"""
        with self.assertRaisesRegex(ValueError, "重复"):
            load_portfolio_from_dict({"holdings": [{"symbol":"SPCX","quantity":1}, {"symbol":"SPCX","quantity":2}]})

    def test_ipo_does_not_claim_six_month_trend_from_83_bars(self):
        """不足 120 根日线时不能把不完整均线叫半年趋势。"""
        frame = pd.DataFrame({"date": pd.date_range("2026-06-12", periods=83, freq="B"),
                              "open": range(100,183), "high": range(101,184), "low": range(99,182),
                              "close": range(100,183), "volume": [1000]*83})
        view = build_portfolio_view(Portfolio("USD",0,[Holding("SPCX",1)]), {"SPCX":MarketSnapshot("SPCX",182)})
        score = score_position(view.positions[0], frame, portfolio_risk_level="balanced", news_risk_flags=[])
        self.assertFalse(any("半年趋势保持向上" in line or "半年趋势仍需修复" in line for line in score.evidence))
        self.assertTrue(any("120" in line for line in score.evidence))


if __name__ == "__main__":
    unittest.main()
