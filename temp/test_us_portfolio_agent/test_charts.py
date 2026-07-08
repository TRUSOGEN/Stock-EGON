"""持仓图表渲染测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
import unittest

import pandas as pd

from us_stock_agent.charts import build_symbol_chart_images, render_symbol_price_volume_png


class FakeMarketProvider:
    """模拟行情 provider。"""

    def __init__(self, frame: pd.DataFrame) -> None:
        """保存历史行情。"""
        self.frame = frame
        self.periods = []

    def fetch_history(self, symbol: str, *, period: str = "6mo") -> pd.DataFrame:
        """记录请求周期并返回行情。"""
        self.periods.append((symbol, period))
        return self.frame


def make_frame(days: int) -> pd.DataFrame:
    """构造价格和成交量行情。"""
    base = datetime(2026, 1, 1)
    rows = []
    for index in range(days):
        open_price = 100 + index * 0.5
        close_price = open_price + (1 if index % 2 == 0 else -0.8)
        rows.append(
            {
                "date": base + timedelta(days=index),
                "open": open_price,
                "high": max(open_price, close_price) + 1.2,
                "low": min(open_price, close_price) - 1.0,
                "close": close_price,
                "volume": 1_000_000 + index * 1000,
            }
        )
    return pd.DataFrame(rows)


class TestCharts(unittest.TestCase):
    """验证单票报价图可以生成 PNG。"""

    def test_render_symbol_price_volume_png_returns_png_bytes(self) -> None:
        """价格折线和成交量报价图应当输出有效 PNG 头。"""
        payload = render_symbol_price_volume_png("NVDA", make_frame(80))

        self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")

    def test_build_symbol_chart_images_fetches_single_quote_chart_period(self) -> None:
        """每个 ticker 只生成一张价格和成交量报价图。"""
        provider = FakeMarketProvider(make_frame(80))

        images = build_symbol_chart_images(["SPEX"], market_provider=provider)

        self.assertEqual(provider.periods, [("SPEX", "3mo")])
        self.assertEqual(images[0].filename, "SPEX-price-volume.png")


if __name__ == "__main__":
    unittest.main()
