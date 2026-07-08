"""美股持仓分析 agent 的核心决策测试。

这些测试不访问真实行情和新闻源，只验证持仓解析、风险暴露、交易动作分层、日报与周报
结构。真实数据源在 CLI smoke test 中单独验证，避免把网络波动当成核心逻辑失败。
"""

from __future__ import annotations

import unittest

import pandas as pd

from us_stock_agent.decision import classify_action, score_position
from us_stock_agent.models import Holding, MarketSnapshot, Portfolio
from us_stock_agent.portfolio import build_portfolio_view, load_portfolio_from_dict
from us_stock_agent.reports import render_daily_report, render_weekly_review


def _trend_frame(start: float, values: list[float]) -> pd.DataFrame:
    """构造标准化日线行情。"""
    closes = [start + value for value in values]
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-06-01", periods=len(closes), freq="D"),
            "open": [close * 0.995 for close in closes],
            "high": [close * 1.015 for close in closes],
            "low": [close * 0.985 for close in closes],
            "close": closes,
            "volume": [1_000_000 + index * 10_000 for index in range(len(closes))],
        }
    )


class DecisionEngineTests(unittest.TestCase):
    """持仓 agent 的核心行为测试集合。"""

    def test_load_portfolio_from_dict_normalizes_symbols_and_cash(self) -> None:
        """持仓配置应标准化 ticker，并保留现金与账户币种。"""
        portfolio = load_portfolio_from_dict(
            {
                "currency": "USD",
                "cash": 4.66,
                "holdings": [
                    {"symbol": "nvda", "quantity": 18, "cost_basis": 180},
                    {"symbol": "spy", "quantity": 3},
                ],
            }
        )

        self.assertEqual(portfolio.currency, "USD")
        self.assertEqual(portfolio.cash, 4.66)
        self.assertEqual([holding.symbol for holding in portfolio.holdings], ["NVDA", "SPY"])
        self.assertEqual(portfolio.holdings[0].quantity, 18)

    def test_build_portfolio_view_calculates_weights_and_unrealized_pnl(self) -> None:
        """组合视图应计算市值、权重和未实现盈亏。"""
        portfolio = Portfolio(
            currency="USD",
            cash=10,
            holdings=[
                Holding(symbol="NVDA", quantity=2, cost_basis=90),
                Holding(symbol="SPY", quantity=1, cost_basis=100),
            ],
        )
        snapshots = {
            "NVDA": MarketSnapshot(symbol="NVDA", price=100, previous_close=98),
            "SPY": MarketSnapshot(symbol="SPY", price=100, previous_close=99),
        }

        view = build_portfolio_view(portfolio, snapshots)

        self.assertAlmostEqual(view.net_liquidation, 310)
        self.assertAlmostEqual(view.positions[0].market_value, 200)
        self.assertAlmostEqual(view.positions[0].unrealized_pnl, 20)
        self.assertGreater(view.positions[0].weight, view.positions[1].weight)

    def test_classify_action_marks_strong_underweight_position_as_add_candidate(self) -> None:
        """趋势强、组合权重未过高且无过热风险时，应归为增持候选。"""
        position = build_portfolio_view(
            Portfolio(currency="USD", cash=1000, holdings=[Holding(symbol="QQQ", quantity=1, cost_basis=100)]),
            {"QQQ": MarketSnapshot(symbol="QQQ", price=120, previous_close=119)},
        ).positions[0]
        score = score_position(
            position,
            _trend_frame(100, list(range(90))),
            portfolio_risk_level="balanced",
            news_risk_flags=[],
        )

        self.assertGreaterEqual(score.total_score, 70)
        self.assertEqual(classify_action(score).action, "add_candidate")

    def test_classify_action_marks_weak_or_risky_position_as_trim_candidate(self) -> None:
        """趋势弱、亏损扩大或有重大风险时，应归为减持候选。"""
        position = build_portfolio_view(
            Portfolio(currency="USD", cash=10, holdings=[Holding(symbol="MRVL", quantity=10, cost_basis=300)]),
            {"MRVL": MarketSnapshot(symbol="MRVL", price=210, previous_close=215)},
        ).positions[0]
        score = score_position(
            position,
            _trend_frame(260, [-index for index in range(90)]),
            portfolio_risk_level="aggressive",
            news_risk_flags=["earnings_miss", "guidance_cut"],
        )

        self.assertLessEqual(score.total_score, 45)
        self.assertEqual(classify_action(score).action, "trim_candidate")

    def test_score_position_absorbs_strategy_skill_signals(self) -> None:
        """评分应吸收多头趋势、低乖离和量价确认等 strategy skill 信号。"""
        position = build_portfolio_view(
            Portfolio(currency="USD", cash=2000, holdings=[Holding(symbol="NVDA", quantity=1, cost_basis=100)]),
            {"NVDA": MarketSnapshot(symbol="NVDA", price=118, previous_close=117)},
        ).positions[0]
        history = _trend_frame(100, [index * 0.2 for index in range(90)])
        history.loc[history.index[-1], "volume"] = history["volume"].rolling(5, min_periods=1).mean().iloc[-1] * 10

        score = score_position(
            position,
            history,
            portfolio_risk_level="balanced",
            news_risk_flags=[],
        )

        evidence = "；".join(score.evidence)
        self.assertIn("MA5/MA10/MA20 多头排列", evidence)
        self.assertIn("均线乖离低于 5%", evidence)
        self.assertIn("放量突破或反弹确认", evidence)

    def test_score_position_treats_negative_events_as_risk_veto(self) -> None:
        """事件驱动信号里，负面事件应优先进入风险扣分和解释。"""
        position = build_portfolio_view(
            Portfolio(currency="USD", cash=2000, holdings=[Holding(symbol="MRVL", quantity=1, cost_basis=100)]),
            {"MRVL": MarketSnapshot(symbol="MRVL", price=118, previous_close=117)},
        ).positions[0]

        score = score_position(
            position,
            _trend_frame(100, [index * 0.2 for index in range(90)]),
            portfolio_risk_level="balanced",
            news_risk_flags=["guidance_cut"],
        )

        self.assertIn("事件驱动风险优先", "；".join(score.evidence))
        self.assertLess(score.risk_score, 80)

    def test_reports_include_holdings_actions_risks_and_source_limits(self) -> None:
        """日报和周报应包含持仓动作、风险、复盘和数据限制。"""
        portfolio = Portfolio(
            currency="USD",
            cash=4.66,
            holdings=[Holding(symbol="TSLA", quantity=8, cost_basis=400)],
        )
        view = build_portfolio_view(
            portfolio,
            {"TSLA": MarketSnapshot(symbol="TSLA", price=414.28, previous_close=419.77)},
        )
        score = score_position(
            view.positions[0],
            _trend_frame(350, list(range(90))),
            portfolio_risk_level="aggressive",
            news_risk_flags=[],
        )
        action = classify_action(score)

        daily = render_daily_report(view=view, scored_actions=[(score, action)], market_notes=["Nasdaq 偏弱"])
        weekly = render_weekly_review(
            view=view,
            scored_actions=[(score, action)],
            weekly_notes=["组合科技股暴露较高"],
        )

        self.assertIn("每日美股持仓简报", daily)
        self.assertIn("TSLA", daily)
        self.assertIn("数据限制", daily)
        self.assertIn("每周持仓复盘", weekly)
        self.assertIn("下周观察清单", weekly)


if __name__ == "__main__":
    unittest.main()
