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
        "## 今日核心结论",
    ]
    buckets = _bucket_actions(scored_actions)
    lines.extend(
        [
            f"- 增持候选: {_symbols_or_none(buckets['add_candidate'])}",
            f"- 减持候选: {_symbols_or_none(buckets['trim_candidate'])}",
            f"- 继续持有: {_symbols_or_none(buckets['hold'])}",
            f"- 重点观察: {_symbols_or_none(buckets['watch'])}",
        ]
    )
    if market_notes:
        lines.append("")
        lines.append("## 市场背景")
        lines.extend(f"- {note}" for note in market_notes)
    if portfolio_risk:
        lines.extend(_portfolio_risk_section(portfolio_risk))
    lines.append("")
    lines.append("## 持仓动作表")
    lines.append("| Ticker | 动作 | 评分 | 权重 | 当日盈亏 | 浮动盈亏 | 主要理由 | 风控/触发条件 |")
    lines.append("|---|---:|---:|---:|---:|---:|---|---|")
    position_by_symbol = {position.symbol: position for position in view.positions}
    for score, action in sorted(scored_actions, key=lambda item: item[0].total_score):
        position = position_by_symbol[score.symbol]
        lines.append(
            "| {symbol} | {label} | {score:.1f} | {weight:.2%} | {day_pnl} | {unrealized} | {reason} | {controls} |".format(
                symbol=score.symbol,
                label=action.label,
                score=score.total_score,
                weight=position.weight,
                day_pnl=_money(position.day_pnl),
                unrealized=_money(position.unrealized_pnl),
                reason="；".join(action.rationale) or "暂无明确证据",
                controls="；".join(action.risk_controls) or "暂无",
            )
        )
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


def _money(value: float | None) -> str:
    """格式化金额。"""
    if value is None:
        return "N/A"
    return f"{value:,.2f}"


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
