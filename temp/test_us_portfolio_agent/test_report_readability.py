"""日报可读性和工作流暂停能力测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from us_stock_agent.decision import classify_action, score_position
from us_stock_agent.models import ActionRecommendation, Holding, MarketSnapshot, Portfolio, PositionScore
from us_stock_agent.portfolio import build_portfolio_view
from us_stock_agent.reports import render_daily_report
from us_stock_agent.schedule_guard import DAILY_SCHEDULES, WEEKLY_SCHEDULES


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
        self.assertIn("## 每只持仓说明", report)
        self.assertIn("目前占组合权重", report)
        self.assertNotIn("一句话:", report)
        self.assertNotIn("| Ticker | 动作 | 评分 | 权重 |", report)
        self.assertNotIn("## 持仓动作表", report)

    def test_daily_report_writes_each_position_as_heading_then_paragraph(self) -> None:
        """单票段落应是标题加自然语言正文，便于图片紧跟在该股票下面。"""
        portfolio = Portfolio(
            currency="USD",
            cash=4.66,
            holdings=[Holding(symbol="NVDA", quantity=10, cost_basis=150)],
            risk_profile="aggressive",
        )
        view = build_portfolio_view(
            portfolio,
            {"NVDA": MarketSnapshot(symbol="NVDA", price=195, previous_close=194)},
        )
        score = PositionScore(
            symbol="NVDA",
            total_score=56,
            trend_score=45,
            momentum_score=64,
            valuation_score=50,
            risk_score=58,
            concentration_score=47,
            evidence=["季度趋势偏弱，收盘价低于 20 日均线", "月度动量仍属健康"],
        )
        action = ActionRecommendation(
            symbol="NVDA",
            action="watch",
            label="重点观察",
            rationale=["季度趋势偏弱，收盘价低于 20 日均线", "月度动量仍属健康"],
            risk_controls=[
                "等待月度趋势或新闻催化进一步确认",
                "观察进入区间: 193.60-198.90",
                "风险位: 186.00",
                "目标观察位: 213.99",
                "失效条件: 跌破 186.00 或出现确认的重大负面事件",
            ],
        )

        report = render_daily_report(view=view, scored_actions=[(score, action)])

        self.assertIn("### NVDA — 重点观察", report)
        self.assertIn("NVDA 目前占组合权重", report)
        self.assertIn("观察进入区间约在 193.60–198.90", report)
        self.assertIn("风险位设在 186.00", report)
        self.assertIn("目标观察位 213.99", report)
        self.assertIn("若股价跌破 186.00 或出现确认的重大负面事件", report)
        section = report.split("### NVDA — 重点观察", 1)[1].split("## 数据限制", 1)[0]
        self.assertNotIn("- 一句话:", section)
        self.assertNotIn("- 当前状态:", section)

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
            label="增持候选",
            rationale=["趋势向上"],
            risk_controls=["等待价格确认"],
        )

        report = render_daily_report(view=view, scored_actions=[(score, action)])

        self.assertIn("增配复核候选", report)
        self.assertIn("增持候选", report)
        self.assertIn("减仓或卖出释放的资金", report)
        self.assertNotIn("可以考虑加一点", report)

    def test_workflow_can_be_paused_with_repository_variable(self) -> None:
        """设置 REPORT_ENABLED=false 应能暂停 GitHub Actions 报告任务。"""
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "us-stock-report.yml").read_text(encoding="utf-8")

        self.assertIn("REPORT_ENABLED", workflow)
        self.assertIn("vars.REPORT_ENABLED != 'false'", workflow)

    def test_workflow_uses_off_peak_beijing_morning_schedule(self) -> None:
        """定时任务应避开整点和半点，降低 GitHub Actions 调度拥堵风险。"""
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "us-stock-report.yml").read_text(encoding="utf-8")

        for schedule in (*DAILY_SCHEDULES, *WEEKLY_SCHEDULES):
            self.assertIn(f'cron: "{schedule}"', workflow)
        self.assertIn("steps.schedule_guard.outputs.report_type == 'daily'", workflow)
        self.assertIn("steps.schedule_guard.outputs.report_type == 'weekly'", workflow)
        self.assertNotIn('cron: "30 0 * * 2-6"', workflow)
        self.assertNotIn('cron: "0 1 * * 6"', workflow)


if __name__ == "__main__":
    unittest.main()
