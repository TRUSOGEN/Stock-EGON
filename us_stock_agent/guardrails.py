"""动作建议 guardrail。

高风险动作必须满足基本数据质量和触发条件。若不满足，本模块会把动作降级为观察，而不是
让报告在证据不足时给出过度确定的增持建议。
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ActionRecommendation, PositionScore
from .quality import DataQuality


@dataclass(frozen=True)
class TriggerLevels:
    """单票动作触发条件。"""

    entry_low: float | None
    entry_high: float | None
    stop_loss: float | None
    target_price: float | None
    invalidation: str | None

    def is_actionable(self) -> bool:
        """检查是否具备进入区间和失效条件。"""
        if self.entry_low is None or self.entry_high is None:
            return False
        if self.entry_low > self.entry_high:
            return False
        if self.stop_loss is None and not self.invalidation:
            return False
        if self.stop_loss is not None and self.stop_loss >= self.entry_high:
            return False
        return True


def apply_action_guardrail(
    action: ActionRecommendation,
    score: PositionScore,
    *,
    data_quality: DataQuality,
    trigger_levels: TriggerLevels | None,
) -> ActionRecommendation:
    """对动作建议应用数据质量和触发条件 guardrail。"""
    if action.action != "add_candidate":
        return _attach_trigger_controls(action, trigger_levels)

    violations: list[str] = []
    if data_quality in {"low", "poor", "unknown"}:
        violations.append("数据质量不足，不能直接列为增持候选")
    if trigger_levels is None or not trigger_levels.is_actionable():
        violations.append("缺少明确触发条件，需先观察确认")
    if score.risk_score < 55:
        violations.append("风险评分不足，需先确认风险解除")

    if violations:
        return ActionRecommendation(
            symbol=action.symbol,
            action="watch",
            label="重点观察",
            rationale=violations + action.rationale[:3],
            risk_controls=action.risk_controls + ["补齐数据质量、进入区间和失效条件后再复核"],
        )
    return _attach_trigger_controls(action, trigger_levels)


def _attach_trigger_controls(
    action: ActionRecommendation,
    trigger_levels: TriggerLevels | None,
) -> ActionRecommendation:
    """把触发条件加入风控说明。"""
    if trigger_levels is None:
        return action
    controls = list(action.risk_controls)
    if trigger_levels.entry_low is not None and trigger_levels.entry_high is not None:
        controls.append(f"观察进入区间: {trigger_levels.entry_low:.2f}-{trigger_levels.entry_high:.2f}")
    if trigger_levels.stop_loss is not None:
        controls.append(f"风险位: {trigger_levels.stop_loss:.2f}")
    if trigger_levels.target_price is not None:
        controls.append(f"目标观察位: {trigger_levels.target_price:.2f}")
    if trigger_levels.invalidation:
        controls.append(f"失效条件: {trigger_levels.invalidation}")
    return ActionRecommendation(
        symbol=action.symbol,
        action=action.action,
        label=action.label,
        rationale=list(action.rationale),
        risk_controls=controls,
    )
