"""美股报告运行编排测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from us_stock_agent.models import Holding, MarketSnapshot, Portfolio
from us_stock_agent.runner import run_report


class FakeMarketProvider:
    """提供稳定离线行情的测试 provider。"""

    def fetch_snapshot(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        """返回每个 ticker 的最新行情快照。"""
        return {symbol: MarketSnapshot(symbol=symbol, price=100.0, previous_close=99.0) for symbol in symbols}

    def fetch_history(self, symbol: str, *, period: str = "6mo") -> pd.DataFrame:
        """返回足够计算趋势、动量和触发位的历史行情。"""
        closes = [90 + index * 0.5 for index in range(60)]
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
                "open": [close * 0.99 for close in closes],
                "high": [close * 1.02 for close in closes],
                "low": [close * 0.98 for close in closes],
                "close": closes,
                "volume": [1_000_000 for _ in closes],
            }
        )


class TimeoutNewsProvider:
    """模拟新闻源超时。"""

    provider_name = "timeout"

    def fetch_news(self, symbols: list[str]) -> dict[str, list[object]]:
        """抛出和真实搜索 API 类似的超时异常。"""
        raise TimeoutError("serpapi read timed out")


class TestRunner(unittest.TestCase):
    """验证报告编排层的失败边界。"""

    def test_report_continues_when_optional_news_provider_times_out(self) -> None:
        """新闻源超时不应阻断行情日报，但必须写入 warning。"""
        portfolio = Portfolio(currency="USD", cash=0, holdings=[Holding(symbol="NVDA", quantity=1)])

        with (
            patch("us_stock_agent.runner.build_news_provider_from_env", return_value=TimeoutNewsProvider()),
            patch("us_stock_agent.runner.news_provider_status", return_value="已检测到新闻源环境变量: SERPAPI_API_KEY。"),
        ):
            result = run_report(portfolio=portfolio, report_type="daily", market_provider=FakeMarketProvider())

        warning_text = "\n".join(result["warnings"])
        report_text = str(result["data"]["report_markdown"])
        self.assertTrue(result["ok"])
        self.assertIn("新闻源调用失败，已跳过新闻增强", warning_text)
        self.assertIn("serpapi read timed out", warning_text)
        self.assertIn("新闻源调用失败，已跳过新闻增强", report_text)


if __name__ == "__main__":
    unittest.main()
