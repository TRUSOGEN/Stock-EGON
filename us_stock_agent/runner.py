"""美股持仓 agent 的运行编排。"""

from __future__ import annotations

from a_stock_quant.output import make_result

from .decision import classify_action, score_position
from .guardrails import TriggerLevels, apply_action_guardrail
from .market_data import MarketDataProvider, YFinanceProvider
from .news import NewsItem, build_news_provider_from_env, news_provider_status
from .portfolio import build_portfolio_view
from .quality import assess_history_quality, normalize_data_quality
from .reports import render_daily_report, render_weekly_review
from .risk import assess_portfolio_risk
from .models import Portfolio


def run_report(
    *,
    portfolio: Portfolio,
    report_type: str,
    market_provider: MarketDataProvider | None = None,
) -> dict[str, object]:
    """运行日报或周报并返回统一 JSON。"""
    provider = market_provider or YFinanceProvider()
    symbols = [holding.symbol for holding in portfolio.holdings]
    snapshots = provider.fetch_snapshot(symbols)
    histories = {symbol: provider.fetch_history(symbol, period="6mo") for symbol in symbols}
    view = build_portfolio_view(portfolio, snapshots)
    portfolio_risk = assess_portfolio_risk(view, risk_profile=portfolio.risk_profile)
    news_warnings: list[str] = []
    try:
        news = build_news_provider_from_env().fetch_news(symbols)
    except Exception as exc:  # noqa: BLE001
        news = {symbol: [] for symbol in symbols}
        news_warnings.append(f"新闻源调用失败，已跳过新闻增强: {exc}")
    scored_actions = []
    for position in view.positions:
        risk_flags = [item.risk_flag for item in news[position.symbol] if item.risk_flag]
        history = histories[position.symbol]
        data_quality = normalize_data_quality(
            {
                "quote": "high" if snapshots.get(position.symbol) else "missing",
                "daily_bars": assess_history_quality(history),
            }
        )
        score = score_position(
            position,
            history,
            portfolio_risk_level=portfolio.risk_profile,
            news_risk_flags=risk_flags,
        )
        raw_action = classify_action(score)
        trigger_levels = _build_trigger_levels(position.symbol, history)
        action = apply_action_guardrail(
            raw_action,
            score,
            data_quality=data_quality,
            trigger_levels=trigger_levels,
        )
        scored_actions.append((score, action))

    market_notes = [news_provider_status()]
    market_notes.extend(news_warnings)
    market_notes.extend(_format_news_notes(news))
    if report_type == "weekly":
        report = render_weekly_review(
            view=view,
            scored_actions=scored_actions,
            portfolio_risk=portfolio_risk,
            weekly_notes=market_notes,
        )
        module = "us_weekly_review"
    elif report_type == "daily":
        report = render_daily_report(
            view=view,
            scored_actions=scored_actions,
            portfolio_risk=portfolio_risk,
            market_notes=market_notes,
        )
        module = "us_daily_report"
    else:
        raise ValueError("report_type 必须是 daily 或 weekly。")
    return make_result(
        module=module,
        data={"report_markdown": report, "symbols": symbols},
        data_time=None,
        source_api="yfinance + configured_news_provider",
        warnings=[
            "免费行情源可能延迟或失败；报告仅供研究复盘，不构成投资建议。",
            *news_warnings,
        ],
    )


def _build_trigger_levels(symbol: str, history) -> TriggerLevels:
    """根据最近 60 个交易日生成偏长期持仓的保守触发条件。"""
    recent = history.tail(min(60, len(history)))
    current = float(recent["close"].iloc[-1])
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())
    entry_low = min(current, support * 1.02)
    entry_high = current * 1.01
    stop_loss = support * 0.98
    target_price = max(resistance, current * 1.15)
    return TriggerLevels(
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        target_price=target_price,
        invalidation=f"{symbol} 跌破 {stop_loss:.2f} 或重大负面事件被确认",
    )


def _format_news_notes(news: dict[str, list[NewsItem]]) -> list[str]:
    """把新闻条目压缩为日报和周报中的市场背景要点。"""
    notes = []
    for symbol, items in news.items():
        if not items:
            continue
        top_titles = "；".join(item.title for item in items[:2])
        notes.append(f"{symbol} 最新资讯: {top_titles}")
    return notes
