"""日报可读性和工作流暂停能力测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from us_stock_agent.decision import classify_action, score_position
from us_stock_agent.models import ActionRecommendation, Holding, MarketSnapshot, Portfolio, PositionScore
from us_stock_agent.portfolio import build_portfolio_view
from us_stock_agent.reports import render_daily_report


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


class TestReportReadability(unittest.TestCase):
    """验证报告用人话表达，并支持暂停服务。"""

    def test_daily_report_uses_narrative_sections_instead_of_wide_table(self) -> None:
        """日报不应再输出难读的大表格。"""
        portfolio = Portfolio(
            currency="USD",
            cash=4.66,
            holdings=[
                Holding(symbol="QQQ", quantity=2.7),
                Holding(symbol="NVDA", quantity=18),
            ],
            risk_profile="aggressive",
        )
        view = build_portfolio_view(
            portfolio,
            {
                "QQQ": MarketSnapshot(symbol="QQQ", price=730, previous_close=725),
                "NVDA": MarketSnapshot(symbol="NVDA", price=195, previous_close=194),
            },
        )
        scored_actions = []
        for position in view.positions:
            score = score_position(
                position,
                _trend_frame(100, list(range(90))),
                portfolio_risk_level="aggressive",
                news_risk_flags=[],
            )
            scored_actions.append((score, classify_action(score)))

        report = render_daily_report(view=view, scored_actions=scored_actions, market_notes=["新闻源未配置。"])

        self.assertIn("## 先看结论", report)
        self.assertIn("## 每只持仓一句话", report)
        self.assertIn("一句话:", report)
        self.assertNotIn("| Ticker | 动作 | 评分 | 权重 |", report)
        self.assertNotIn("## 持仓动作表", report)

    def test_daily_report_frames_add_candidates_as_rebalance_not_cash_spend(self) -> None:
        """买入候选应明确来自调仓资金，不默认消耗现金。"""
        portfolio = Portfolio(
            currency="USD",
            cash=4.66,
            holdings=[Holding(symbol="NVDA", quantity=5)],
            risk_profile="aggressive",
        )
        view = build_portfolio_view(
            portfolio,
            {"NVDA": MarketSnapshot(symbol="NVDA", price=195, previous_close=194)},
        )
        score = PositionScore(
            symbol="NVDA",
            total_score=82,
            trend_score=25,
            momentum_score=20,
            valuation_score=15,
            risk_score=15,
            concentration_score=7,
            evidence=["趋势向上"],
        )
        action = ActionRecommendation(
            symbol="NVDA",
            action="add_candidate",
            label="换仓候选",
            rationale=["趋势向上"],
            risk_controls=["等待价格确认"],
        )

        report = render_daily_report(view=view, scored_actions=[(score, action)])

        self.assertIn("换仓候选", report)
        self.assertIn("减仓或卖出释放的资金", report)
        self.assertNotIn("可以考虑加一点", report)

    def test_workflow_can_be_paused_with_repository_variable(self) -> None:
        """设置 REPORT_ENABLED=false 应能暂停 GitHub Actions 报告任务。"""
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "us-stock-report.yml").read_text(encoding="utf-8")

        self.assertIn("REPORT_ENABLED", workflow)
        self.assertIn("vars.REPORT_ENABLED != 'false'", workflow)


if __name__ == "__main__":
    unittest.main()
