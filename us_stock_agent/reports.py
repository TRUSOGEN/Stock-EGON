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
        f"# 每日美股持仓简报 | {current_date.isoformat()}",
        "",
        f"组合净值: {view.net_liquidation:,.2f} {view.currency} | 现金: {view.cash:,.2f} | 现金权重: {view.cash_weight:.2%}",
        "",
        "## 先看结论",
    ]
    buckets = _bucket_actions(scored_actions)
    lines.extend(
        [
            f"- 可以考虑加一点: {_symbols_or_none(buckets['add_candidate'])}",
            f"- 需要减仓或复核: {_symbols_or_none(buckets['trim_candidate'])}",
            f"- 先拿着: {_symbols_or_none(buckets['hold'])}",
            f"- 先别动，只观察: {_symbols_or_none(buckets['watch'])}",
        ]
    )
    if market_notes:
        lines.append("")
        lines.append("## 市场背景")
        lines.extend(f"- {note}" for note in market_notes)
    if portfolio_risk:
        lines.extend(_portfolio_risk_section(portfolio_risk))
    lines.append("")
    lines.append("## 每只持仓一句话")
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
        "## 本周复盘重点",
    ]
    lines.extend(f"- {note}" for note in (weekly_notes or ["复盘技术趋势、组合集中度和下周事件风险。"]))
    if portfolio_risk:
        lines.extend(_portfolio_risk_section(portfolio_risk))
    lines.append("")
    lines.append("## 下周观察清单")
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
        f"### {score.symbol} - {action.label}",
        f"- 一句话: {_plain_action_sentence(action.action)}",
        f"- 当前状态: 权重 {position.weight:.2%}，评分 {score.total_score:.1f}，当日盈亏 {_money_label(position.day_pnl)}，浮动盈亏 {_money_label(position.unrealized_pnl)}。",
        f"- 为什么: {_join_or_none(action.rationale)}。",
        f"- 怎么盯: {_join_or_none(action.risk_controls)}。",
    ]


def _plain_action_sentence(action: str) -> str:
    """把动作标签翻译成更接近人话的解释。"""
    if action == "add_candidate":
        return "走势还可以，可以放进加仓候选，但等价格确认，别追高。"
    if action == "trim_candidate":
        return "风险或趋势不够好，先复核仓位，必要时减一点。"
    if action == "hold":
        return "先拿着，按风险位盯，不因为一天波动乱动。"
    return "信息还不够明确，先观察，不急着买卖。"


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
