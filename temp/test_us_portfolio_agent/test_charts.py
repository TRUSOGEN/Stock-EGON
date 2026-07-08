"""持仓图表渲染测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
import unittest

import pandas as pd

from us_stock_agent.charts import render_symbol_triptych_png


class TestCharts(unittest.TestCase):
    """验证单票三视角图表可以生成 PNG。"""

    def test_render_symbol_triptych_png_returns_png_bytes(self) -> None:
        """周、月、年三联图应当输出有效 PNG 头。"""
        base = datetime(2026, 1, 1)

        def make_frame(days: int) -> pd.DataFrame:
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

        payload = render_symbol_triptych_png(
            "NVDA",
            {
                "1W": make_frame(5),
                "1M": make_frame(22),
                "1Y": make_frame(120),
            },
        )

        self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
