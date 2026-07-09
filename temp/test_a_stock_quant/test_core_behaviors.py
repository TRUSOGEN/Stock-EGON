"""A 股量化工具的核心行为测试。

这些测试覆盖不依赖外部行情源的纯计算逻辑：技术指标、信号生成、回测成交规则和
统一 JSON 输出骨架。外部 AKShare 接口的稳定性不在单元测试里假设，而是在 CLI smoke
test 中以真实错误或真实数据暴露。
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime

import pandas as pd

from a_stock_quant.analysis import analyze_stock, screen_stocks
from a_stock_quant.backtesting import run_backtest
from a_stock_quant.indicators import compute_indicators
from a_stock_quant.output import make_result


def _sample_daily_frame() -> pd.DataFrame:
    """构造一段趋势先弱后强的日线数据，用于可重复的指标和回测测试。"""
    closes = [
        10.0,
        9.8,
        9.7,
        9.9,
        10.2,
        10.5,
        10.9,
        11.2,
        11.5,
        11.9,
        12.2,
        12.6,
        12.9,
        13.2,
        13.5,
        13.1,
        12.8,
        13.0,
        13.4,
        13.8,
        14.1,
        14.5,
        14.9,
        15.2,
        15.6,
    ]
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "open": [value * 0.99 for value in closes],
            "high": [value * 1.02 for value in closes],
            "low": [value * 0.98 for value in closes],
            "close": closes,
            "volume": [10000 + index * 300 for index in range(len(closes))],
            "turnover": [1.5 + index * 0.05 for index in range(len(closes))],
        }
    )


class CoreBehaviorTests(unittest.TestCase):
    """核心行为测试集合。"""

    def test_compute_indicators_adds_expected_columns_and_latest_signal(self) -> None:
        """技术指标计算应补齐常用列，并给出可解释的最新信号。"""
        indicators = compute_indicators(_sample_daily_frame())
        latest = indicators.iloc[-1]

        self.assertTrue(
            {
                "ma5",
                "ma10",
                "ma20",
                "ma60",
                "ma120",
                "ma200",
                "macd",
                "rsi6",
                "rsi24",
                "boll_mid",
                "volume_ratio",
                "volume_ratio_20",
            }.issubset(indicators.columns)
        )
        self.assertGreater(latest["ma5"], latest["ma20"])
        self.assertGreaterEqual(latest["rsi6"], 0)
        self.assertLessEqual(latest["rsi6"], 100)
        self.assertGreaterEqual(latest["rsi24"], 0)
        self.assertLessEqual(latest["rsi24"], 100)
        self.assertGreater(latest["volume_ratio"], 0)
        self.assertGreater(latest["volume_ratio_20"], 0)

    def test_analyze_stock_returns_structured_diagnosis_without_buy_sell_orders(self) -> None:
        """个股诊断应返回技术信号和观察点，不输出买卖指令。"""
        diagnosis = analyze_stock("000001", "平安银行", _sample_daily_frame())

        self.assertEqual(diagnosis["code"], "000001")
        self.assertEqual(diagnosis["name"], "平安银行")
        self.assertGreaterEqual(diagnosis["score"], 0)
        self.assertLessEqual(diagnosis["score"], 100)
        self.assertIn(diagnosis["trend"], {"偏多", "偏空", "震荡"})
        self.assertIn(diagnosis["signal"], {"偏多", "偏空", "中性"})
        self.assertNotIn("买入", json.dumps(diagnosis, ensure_ascii=False))
        self.assertNotIn("卖出", json.dumps(diagnosis, ensure_ascii=False))
        self.assertLess(diagnosis["key_levels"]["support"], diagnosis["key_levels"]["resistance"])

    def test_screen_stocks_ranks_candidates_by_multi_factor_score(self) -> None:
        """多因子选股应按综合评分排序并保留过滤后的候选股。"""
        weak_frame = _sample_daily_frame().assign(
            close=lambda frame: frame["close"].iloc[::-1].to_numpy(),
            volume=8000,
            turnover=0.8,
        )
        candidates = [
            {
                "code": "000001",
                "name": "平安银行",
                "pe": 6.5,
                "pb": 0.6,
                "history": _sample_daily_frame(),
            },
            {"code": "600000", "name": "浦发银行", "pe": 12.0, "pb": 0.9, "history": weak_frame},
        ]

        result = screen_stocks(candidates, top=2, strategy="multi_factor", min_price=2.0)

        self.assertEqual(result["strategy"], "multi_factor")
        self.assertEqual([item["rank"] for item in result["results"]], [1, 2])
        self.assertGreaterEqual(result["results"][0]["score"], result["results"][1]["score"])
        self.assertEqual(result["results"][0]["code"], "000001")

    def test_backtest_uses_next_day_execution_and_reports_risk_metrics(self) -> None:
        """回测应使用下一交易日成交，输出收益、回撤、胜率、夏普等指标。"""
        backtest = run_backtest(_sample_daily_frame(), strategy="ma_cross", initial_cash=100000)

        self.assertEqual(backtest["strategy"], "ma_cross")
        self.assertGreaterEqual(backtest["metrics"]["trade_count"], 1)
        self.assertGreater(backtest["metrics"]["total_return"], -1)
        self.assertLess(backtest["metrics"]["total_return"], 10)
        self.assertGreaterEqual(backtest["metrics"]["max_drawdown"], 0)
        self.assertLessEqual(backtest["metrics"]["max_drawdown"], 1)
        self.assertGreaterEqual(backtest["metrics"]["win_rate"], 0)
        self.assertLessEqual(backtest["metrics"]["win_rate"], 1)
        self.assertIn("annual_return", backtest["metrics"])
        self.assertIn("sharpe", backtest["metrics"])

    def test_make_result_preserves_data_timestamp_and_warnings(self) -> None:
        """统一输出骨架应显式保留数据时间、抓取时间、来源和风险提示。"""
        result = make_result(
            module="diagnosis",
            data={"code": "000001"},
            data_time="2026-01-31",
            source_api="ak.stock_zh_a_hist",
            warnings=["AKShare 数据仅供研究参考"],
            fetched_at=datetime(2026, 2, 1, 9, 30, 0),
        )

        self.assertIs(result["ok"], True)
        self.assertEqual(result["module"], "diagnosis")
        self.assertEqual(result["data_time"], "2026-01-31")
        self.assertEqual(result["source_api"], "ak.stock_zh_a_hist")
        self.assertEqual(result["warnings"], ["AKShare 数据仅供研究参考"])
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
