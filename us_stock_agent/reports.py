"""美股持仓日报与周报渲染。"""

from __future__ import annotations

from datetime import date

from .models import ActionRecommendation, PortfolioView, PositionScore


def render_daily_report(
    *,
    view: PortfolioView,
    scored_actions: list[tuple[PositionScore, ActionRecommendation]],
    portfolio_risk: dict[str, object] | None = None,
    market_notes: list[str] | None = None,
    report_date: date | None = None,
) -> str:
    """渲染每日美股持仓简报。"""
    current_date = report_date or date.today()
    lines = [
        f"# 长期美股持仓日报 | {current_date.isoformat()}",
        "",
        f"组合净值: {view.net_liquidation:,.2f} {view.currency} | 现金: {view.cash:,.2f} | 现金权重: {view.cash_weight:.2%}",
        "",
        "## 先看结论",
    ]
    buckets = _bucket_actions(scored_actions)
    lines.extend(
        [
            f"- 增配复核候选: {_symbols_or_none(buckets['add_candidate'])}",
            f"- 降权复核候选: {_symbols_or_none(buckets['trim_candidate'])}",
            f"- 继续持有: {_symbols_or_none(buckets['hold'])}",
            f"- 重点观察: {_symbols_or_none(buckets['watch'])}",
            "- 周期口径: 动作标签用于 1 个月、1 个季度和 1 年视角的持仓复盘，不是日内交易信号。",
            "- 再平衡原则: 增配候选默认用降权或卖出释放的资金承接，不按新增现金处理。",
        ]
    )
    if market_notes:
        lines.append("")
        lines.append("## 市场背景")
        lines.extend(f"- {note}" for note in market_notes)
    if portfolio_risk:
        lines.extend(_portfolio_risk_section(portfolio_risk))
    lines.append("")
    lines.append("## 每只持仓说明")
    position_by_symbol = {position.symbol: position for position in view.positions}
    for score, action in sorted(scored_actions, key=lambda item: _action_sort_key(item[1].action)):
        position = position_by_symbol[score.symbol]
        lines.extend(_position_plain_language_section(score, action, position))
    lines.extend(_source_limit_section())
    return "\n".join(lines)


def render_weekly_review(
    *,
    view: PortfolioView,
    scored_actions: list[tuple[PositionScore, ActionRecommendation]],
    portfolio_risk: dict[str, object] | None = None,
    weekly_notes: list[str] | None = None,
    report_date: date | None = None,
) -> str:
    """渲染每周持仓复盘。"""
    current_date = report_date or date.today()
    lines = [
        f"# 每周持仓复盘 | {current_date.isoformat()}",
        "",
        f"组合净值: {view.net_liquidation:,.2f} {view.currency} | 投入市值: {view.invested_value:,.2f} | 现金权重: {view.cash_weight:.2%}",
        "",
        "## 中长期复盘重点",
    ]
    lines.extend(f"- {note}" for note in (weekly_notes or ["复盘月度趋势、季度趋势、组合集中度和未来事件风险。"]))
    lines.append("- 周期口径: 周报用于更新 1 个月、1 个季度和 1 年视角的持仓计划。")
    lines.append("- 再平衡原则: 新增仓位默认来自降权或卖出释放的资金，不按新增现金处理。")
    if portfolio_risk:
        lines.extend(_portfolio_risk_section(portfolio_risk))
    lines.append("")
    lines.append("## 中长期观察清单")
    for score, action in sorted(scored_actions, key=lambda item: item[0].total_score):
        lines.append(
            f"- {score.symbol}: {action.label}，评分 {score.total_score:.1f}；风控: {'；'.join(action.risk_controls)}"
        )
    lines.append("")
    lines.append("## 组合结构")
    for position in view.positions:
        lines.append(f"- {position.symbol}: 权重 {position.weight:.2%}，市值 {position.market_value:,.2f}")
    lines.extend(_source_limit_section())
    return "\n".join(lines)


def _bucket_actions(
    scored_actions: list[tuple[PositionScore, ActionRecommendation]],
) -> dict[str, list[str]]:
    """按动作分组 ticker。"""
    buckets = {"add_candidate": [], "trim_candidate": [], "hold": [], "watch": []}
    for _, action in scored_actions:
        buckets[action.action].append(action.symbol)
    return buckets


def _symbols_or_none(symbols: list[str]) -> str:
    """格式化 ticker 列表。"""
    return ", ".join(symbols) if symbols else "无"


def _position_plain_language_section(score: PositionScore, action: ActionRecommendation, position) -> list[str]:
    """把单票动作写成适合邮件阅读的自然语言。"""
    return [
        "",
        f"### {score.symbol} — {action.label}",
        _position_narrative(score, action, position),
    ]


def _position_narrative(score: PositionScore, action: ActionRecommendation, position) -> str:
    """生成单票自然语言段落。"""
    parts = [
        f"{score.symbol} 目前占组合权重 {position.weight:.2%}，{_pnl_narrative(position.unrealized_pnl)}。",
        _signal_narrative(score, action),
        _action_narrative(action.action, action.label),
    ]
    levels = _extract_control_levels(action.risk_controls)
    levels_text = _levels_narrative(levels)
    if levels_text:
        parts.append(f"需要盯住的关键区间：{levels_text}。")
    invalidation_text = _invalidation_narrative(levels.get("invalidation"))
    if invalidation_text:
        parts.append(f"{invalidation_text}，需重新评估。")
    else:
        parts.append(f"后续风控重点是{_join_or_none(action.risk_controls)}。")
    return "".join(parts)


def _pnl_narrative(value: float | None) -> str:
    """把浮动盈亏写成人话。"""
    if value is None:
        return "未填成本价，暂不计算浮动盈亏"
    if value > 0:
        return f"已有浮盈 {_money(value)}"
    if value < 0:
        return f"目前浮亏 {_money(abs(value))}"
    return "当前浮动盈亏接近持平"


def _signal_narrative(score: PositionScore, action: ActionRecommendation) -> str:
    """描述当前信号强弱。"""
    evidence = _join_or_none(action.rationale or score.evidence)
    return f"当前主要信号是{evidence}。"


def _action_narrative(action: str, label: str) -> str:
    """解释当前动作标签。"""
    if action == "add_candidate":
        return f"因此列为{label}，若后续增持，默认用减仓或卖出释放的资金承接，并按月度或季度节奏复核。"
    if action == "trim_candidate":
        return f"因此列为{label}，先复核仓位和风险来源，必要时分批处理。"
    if action == "hold":
        return f"因此列为{label}，继续按风险位跟踪，不因为单日波动乱动。"
    return f"当前信息不足以支持调整持仓，因此列为{label}，等待月度趋势或新闻催化进一步明朗。"


def _extract_control_levels(risk_controls: list[str]) -> dict[str, str]:
    """从风控说明中提取价格区间、风险位、目标位和失效条件。"""
    levels: dict[str, str] = {}
    for item in risk_controls:
        if item.startswith("观察进入区间:"):
            levels["entry"] = item.split(":", 1)[1].strip().replace("-", "–")
        elif item.startswith("风险位:"):
            levels["risk"] = item.split(":", 1)[1].strip()
        elif item.startswith("目标观察位:"):
            levels["target"] = item.split(":", 1)[1].strip()
        elif item.startswith("失效条件:"):
            levels["invalidation"] = item.split(":", 1)[1].strip()
    return levels


def _levels_narrative(levels: dict[str, str]) -> str:
    """把关键价位拼成自然语言。"""
    items = []
    if entry := levels.get("entry"):
        items.append(f"观察进入区间约在 {entry}")
    if risk := levels.get("risk"):
        items.append(f"风险位设在 {risk}")
    if target := levels.get("target"):
        items.append(f"目标观察位 {target}")
    return "，".join(items)


def _invalidation_narrative(invalidation: str | None) -> str:
    """把失效条件拼成自然语言。"""
    if not invalidation:
        return ""
    if invalidation.startswith("跌破"):
        condition = f"股价{invalidation}"
    else:
        condition = invalidation
    return f"若{condition}，则当前观察逻辑失效"


def _money(value: float | None) -> str:
    """格式化金额。"""
    if value is None:
        return "N/A"
    return f"{value:,.2f}"


def _money_label(value: float | None) -> str:
    """格式化适合人读的金额。"""
    if value is None:
        return "未填成本，暂不计算"
    return f"{value:,.2f}"


def _join_or_none(items: list[str]) -> str:
    """连接理由或风控说明。"""
    return "；".join(items) if items else "暂无明确证据"


def _action_sort_key(action: str) -> int:
    """按读者最关心的动作排序。"""
    order = {"trim_candidate": 0, "add_candidate": 1, "watch": 2, "hold": 3}
    return order.get(action, 9)


def _source_limit_section() -> list[str]:
    """固定的数据限制说明。"""
    return [
        "",
        "## 数据限制",
        "- 免费行情源可能有延迟、字段缺失、限流或上游变更。",
        "- 新闻源未配置时，事件风险只能来自手工输入或空列表。",
        "- 本报告是研究辅助，不构成投资建议或交易指令。",
    ]


def _portfolio_risk_section(portfolio_risk: dict[str, object]) -> list[str]:
    """格式化组合风险。"""
    concentration = portfolio_risk.get("concentration", {})
    cash = portfolio_risk.get("cash", {})
    diversification = portfolio_risk.get("diversification", {})
    top_symbols = concentration.get("top_symbols", []) if isinstance(concentration, dict) else []
    if isinstance(top_symbols, list):
        top_symbols_text = ", ".join(str(item) for item in top_symbols) or "无"
    else:
        top_symbols_text = "无"
    return [
        "",
        "## 组合风险",
        f"- 单票集中度预警: {'是' if isinstance(concentration, dict) and concentration.get('alert') else '否'}；超阈值标的: {top_symbols_text}",
        f"- 现金不足预警: {'是' if isinstance(cash, dict) and cash.get('alert') else '否'}；现金权重: {_pct(cash.get('cash_weight') if isinstance(cash, dict) else None)}",
        f"- 持仓数量预警: {'是' if isinstance(diversification, dict) and diversification.get('alert') else '否'}；持仓数量: {diversification.get('position_count') if isinstance(diversification, dict) else 'N/A'}",
    ]


def _pct(value: object) -> str:
    """格式化比例。"""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "N/A"
