"""持仓评分和动作分层。

本模块把中期趋势、较长周期动量、组合权重、新闻风险和持仓盈亏合成为研究动作。分数用于
1 个月、1 个季度和 1 年视角的排序和复盘，不等同于无条件交易指令。
"""

from __future__ import annotations

import pandas as pd

from a_stock_quant.indicators import compute_indicators

from .models import ActionRecommendation, PositionScore, PositionView


def score_position(
    position: PositionView,
    history: pd.DataFrame,
    *,
    portfolio_risk_level: str,
    news_risk_flags: list[str],
) -> PositionScore:
    """为单个持仓生成综合评分。"""
    indicators = compute_indicators(history)
    latest = indicators.iloc[-1]
    trend_score = 50.0
    momentum_score = 50.0
    valuation_score = 50.0
    risk_score = 80.0
    concentration_score = 75.0
    evidence: list[str] = []

    if latest["ma20"] > latest["ma60"]:
        trend_score += 18
        evidence.append("季度趋势向上")
    else:
        trend_score -= 18
        evidence.append("季度趋势偏弱")
    if latest["ma60"] > latest["ma120"]:
        trend_score += 8
        evidence.append("半年趋势保持向上")
    elif latest["ma60"] < latest["ma120"]:
        trend_score -= 8
        evidence.append("半年趋势仍需修复")
    if latest["close"] > latest["ma20"]:
        trend_score += 6
        evidence.append("收盘价位于 MA20 上方")
    else:
        trend_score -= 6
        evidence.append("收盘价跌破 MA20")

    previous = indicators.iloc[-2] if len(indicators) >= 2 else latest
    if latest["ma5"] >= latest["ma10"] >= latest["ma20"] and latest["ma20"] >= previous["ma20"]:
        trend_score += 5
        evidence.append("短中期均线配合季度趋势")
    elif latest["ma5"] < latest["ma10"] < latest["ma20"]:
        trend_score -= 5
        evidence.append("短中期均线空头排列")

    ma20_bias = (latest["close"] / latest["ma20"] - 1) if latest["ma20"] else 0.0
    if 0 <= ma20_bias <= 0.05:
        trend_score += 6
        evidence.append("均线乖离低于 5%，位置不算追高")
    elif ma20_bias > 0.1:
        momentum_score -= 8
        evidence.append("价格距离 MA20 过远，追高风险上升")

    if 42 <= latest["rsi24"] <= 68:
        momentum_score += 12
        evidence.append("月度动量健康")
    elif latest["rsi24"] > 78:
        momentum_score -= 10
        evidence.append("月度动量过热")
    elif latest["rsi24"] < 38:
        momentum_score -= 10
        evidence.append("月度动量偏弱")
    if latest["volume_ratio_20"] > 1.6 and latest["close"] >= indicators["close"].iloc[-2]:
        momentum_score += 9
        evidence.append("20 日量能支持趋势延续")
    elif latest["volume_ratio_20"] > 1.15 and latest["close"] >= indicators["close"].iloc[-2]:
        momentum_score += 5
        evidence.append("上涨伴随温和放量")

    if position.unrealized_pnl_pct is not None:
        if position.unrealized_pnl_pct < -0.12:
            risk_score -= 22
            evidence.append("持仓亏损超过 12%")
        elif position.unrealized_pnl_pct > 0.2:
            risk_score += 6
            evidence.append("持仓已有显著浮盈")
    if news_risk_flags:
        risk_score -= min(30, 10 * len(news_risk_flags))
        evidence.append("事件驱动风险优先，存在新闻或事件风险标记")

    if position.weight > _max_single_name_weight(portfolio_risk_level):
        concentration_score -= 26
        evidence.append("单票权重超过风险偏好上限")
    elif position.weight < 0.12:
        concentration_score += 24
        evidence.append("组合权重仍较低")
    if position.target_weight is not None and position.weight > position.target_weight * 1.25:
        concentration_score -= 18
        evidence.append("当前权重显著高于目标权重")

    total = (
        _clip(trend_score) * 0.34
        + _clip(momentum_score) * 0.14
        + _clip(valuation_score) * 0.08
        + _clip(risk_score) * 0.24
        + _clip(concentration_score) * 0.2
    )
    return PositionScore(
        symbol=position.symbol,
        total_score=round(_clip(total), 2),
        trend_score=round(_clip(trend_score), 2),
        momentum_score=round(_clip(momentum_score), 2),
        valuation_score=round(_clip(valuation_score), 2),
        risk_score=round(_clip(risk_score), 2),
        concentration_score=round(_clip(concentration_score), 2),
        evidence=evidence,
    )


def classify_action(score: PositionScore) -> ActionRecommendation:
    """把评分映射为研究动作。"""
    if score.total_score >= 70 and score.risk_score >= 55 and score.concentration_score >= 55:
        return ActionRecommendation(
            symbol=score.symbol,
            action="add_candidate",
            label="增持候选",
            rationale=score.evidence[:4],
            risk_controls=["等待月度趋势和风险位确认，不因单日波动追价", "单票权重不超过预设上限"],
        )
    if score.total_score <= 45 or score.risk_score <= 45 or score.concentration_score <= 45:
        return ActionRecommendation(
            symbol=score.symbol,
            action="trim_candidate",
            label="减持候选",
            rationale=score.evidence[:4],
            risk_controls=["优先确认是否跌破关键均线或事件风险兑现", "分批处理，避免单点情绪化交易"],
        )
    if score.total_score < 58:
        return ActionRecommendation(
            symbol=score.symbol,
            action="watch",
            label="重点观察",
            rationale=score.evidence[:4],
            risk_controls=["等待月度趋势或事件风险进一步确认", "更新风险位、目标观察位和失效条件"],
        )
    return ActionRecommendation(
        symbol=score.symbol,
        action="hold",
        label="继续持有",
        rationale=score.evidence[:4],
        risk_controls=["维持月度复盘，若跌破 MA60 或出现重大负面新闻则复核"],
    )


def _max_single_name_weight(risk_level: str) -> float:
    """根据风险偏好返回单票权重上限。"""
    if risk_level == "aggressive":
        return 0.38
    if risk_level == "conservative":
        return 0.22
    return 0.3


def _clip(value: float) -> float:
    """限制分数区间。"""
    return max(0.0, min(100.0, value))
