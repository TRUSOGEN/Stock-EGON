"""美股持仓 agent 的 guardrail、数据质量和组合风险测试。

这些测试吸收参考项目的关键思想：动作建议必须有数据质量等级、触发条件和风险约束；
组合层必须报告集中度与现金风险。测试保持离线，不依赖外部行情。
"""

from __future__ import annotations

import unittest

from us_stock_agent.guardrails import apply_action_guardrail
from us_stock_agent.models import ActionRecommendation, Holding, MarketSnapshot, Portfolio, PositionScore
from us_stock_agent.portfolio import build_portfolio_view
from us_stock_agent.quality import normalize_data_quality
from us_stock_agent.risk import assess_portfolio_risk
from us_stock_agent.reports import render_daily_report


class GuardrailAndRiskTests(unittest.TestCase):
    """动作 guardrail 和组合风险测试集合。"""

    def test_normalize_data_quality_uses_worst_explicit_level(self) -> None:
        """数据质量应取显式输入中的最差等级。"""
        quality = normalize_data_quality(
            {
                "quote": "high",
                "daily_bars": {"level": "stale"},
                "news": "missing",
            }
        )

        self.assertEqual(quality, "poor")

    def test_add_candidate_is_downgraded_when_data_quality_is_low(self) -> None:
        """低质量数据不能直接产生增持候选。"""
        action = ActionRecommendation(
            symbol="NVDA",
            action="add_candidate",
            label="增持候选",
            rationale=["趋势向上"],
            risk_controls=["单票权重不超过上限"],
        )
        score = PositionScore(
            symbol="NVDA",
            total_score=78,
            trend_score=80,
            momentum_score=75,
            valuation_score=50,
            risk_score=72,
            concentration_score=70,
            evidence=["趋势向上"],
        )

        guarded = apply_action_guardrail(action, score, data_quality="low", trigger_levels=None)

        self.assertEqual(guarded.action, "watch")
        self.assertIn("数据质量不足", "；".join(guarded.rationale))

    def test_add_candidate_requires_trigger_levels(self) -> None:
        """增持候选必须带有进入区间、失效条件和风险位。"""
        action = ActionRecommendation(
            symbol="QQQ",
            action="add_candidate",
            label="增持候选",
            rationale=["趋势向上"],
            risk_controls=["单票权重不超过上限"],
        )
        score = PositionScore(
            symbol="QQQ",
            total_score=76,
            trend_score=78,
            momentum_score=74,
            valuation_score=50,
            risk_score=70,
            concentration_score=72,
            evidence=["趋势向上"],
        )

        guarded = apply_action_guardrail(action, score, data_quality="high", trigger_levels=None)

        self.assertEqual(guarded.action, "watch")
        self.assertIn("缺少明确触发条件", "；".join(guarded.rationale))

    def test_portfolio_risk_flags_concentration_and_low_cash(self) -> None:
        """组合风险应标记单票集中和现金不足。"""
        view = build_portfolio_view(
            Portfolio(
                currency="USD",
                cash=4.66,
                risk_profile="balanced",
                holdings=[
                    Holding(symbol="NVDA", quantity=18),
                    Holding(symbol="SPY", quantity=1),
                ],
            ),
            {
                "NVDA": MarketSnapshot(symbol="NVDA", price=190, previous_close=188),
                "SPY": MarketSnapshot(symbol="SPY", price=750, previous_close=748),
            },
        )

        risk = assess_portfolio_risk(view, risk_profile="balanced")

        self.assertTrue(risk["concentration"]["alert"])
        self.assertTrue(risk["cash"]["alert"])
        self.assertIn("NVDA", risk["concentration"]["top_symbols"])

    def test_daily_report_renders_portfolio_risk_and_trigger_controls(self) -> None:
        """日报应展示组合风险和 guardrail 后的触发风控。"""
        view = build_portfolio_view(
            Portfolio(currency="USD", cash=5, holdings=[Holding(symbol="NVDA", quantity=10)]),
            {"NVDA": MarketSnapshot(symbol="NVDA", price=190, previous_close=188)},
        )
        risk = assess_portfolio_risk(view, risk_profile="balanced")
        action = ActionRecommendation(
            symbol="NVDA",
            action="watch",
            label="重点观察",
            rationale=["数据质量不足，不能直接列为增持候选"],
            risk_controls=["观察进入区间: 180.00-190.00", "风险位: 170.00"],
        )
        score = PositionScore(
            symbol="NVDA",
            total_score=68,
            trend_score=70,
            momentum_score=65,
            valuation_score=50,
            risk_score=60,
            concentration_score=40,
        )

        report = render_daily_report(view=view, scored_actions=[(score, action)], portfolio_risk=risk)

        self.assertIn("组合风险", report)
        self.assertIn("单票集中度预警", report)
        self.assertIn("观察进入区间", report)


if __name__ == "__main__":
    unittest.main()
