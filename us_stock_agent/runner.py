"""美股持仓 agent 的运行编排。"""

from __future__ import annotations

from dataclasses import asdict
import json

from a_stock_quant.indicators import compute_indicators, safe_float
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
        news_provider = build_news_provider_from_env()
        news = news_provider.fetch_news(symbols)
        news_warnings.extend(getattr(news_provider, "warnings", []))
    except Exception as exc:  # noqa: BLE001
        news = {symbol: [] for symbol in symbols}
        news_warnings.append(f"新闻源调用失败，已跳过新闻增强: {exc}")
    scored_actions = []
    evidence = {}
    for position in view.positions:
        items = news.get(position.symbol, [])
        risk_flags = [item.risk_flag for item in items if item.risk_flag]
        history = histories[position.symbol]
        data_quality = normalize_data_quality(
            {
                "quote": snapshots[position.symbol].quality,
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
        latest = compute_indicators(history).iloc[-1]
        evidence[position.symbol] = {
            "quote": {"id": f"{position.symbol}:quote", **asdict(snapshots[position.symbol])},
            "position": {"id": f"{position.symbol}:position", **asdict(position)},
            "technical": {
                "id": f"{position.symbol}:technical", "bars": len(history),
                "data_time": str(history["date"].iloc[-1]),
                "ma20": safe_float(latest["ma20"]) if len(history) >= 20 else None,
                "ma60": safe_float(latest["ma60"]) if len(history) >= 60 else None,
                "ma120": safe_float(latest["ma120"]) if len(history) >= 120 else None,
                "rsi24": safe_float(latest["rsi24"]) if len(history) >= 25 else None,
                "volume_ratio_20": safe_float(latest["volume_ratio_20"]) if len(history) >= 20 else None,
                "data_quality": data_quality,
            },
            "rules": {"id": f"{position.symbol}:rules", "score": asdict(score), "action": asdict(action),
                      "validation": "heuristic_not_backtested", "valuation": "not_available"},
            "news": [{"id": f"{position.symbol}:news:{index}", **asdict(item),
                      "verification": "search_result_not_verified_full_text"} for index, item in enumerate(items)],
        }

    market_notes = [news_provider_status()]
    market_notes.extend(news_warnings)
    market_notes.extend(_format_news_notes(news))
    market_notes.extend(warning for quote in snapshots.values() for warning in quote.warnings)
    market_notes.append("常规盘已收盘价格；盘前、盘后与隔夜价格不计入组合估值。技术区间是历史统计参考，不是预测目标价。")
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
    quote_lines = ["## 行情核对（程序计算）", ""]
    for symbol in symbols:
        quote = snapshots[symbol]
        quote_lines.append(f"- {symbol} / {quote.name or '名称未提供'}：收盘 {quote.price:.4f} {quote.currency}；行情时间 {quote.data_time or '未提供'}；来源 {quote.source}；口径 {quote.price_basis}。")
    report = "\n".join(quote_lines) + "\n\n" + report
    return make_result(
        module=module,
        data={"report_markdown": report, "symbols": symbols, "evidence": evidence,
              "chart_history": {symbol: json.loads(history.to_json(orient="records", date_format="iso")) for symbol, history in histories.items()}},
        data_time=min((quote.data_time for quote in snapshots.values() if quote.data_time), default=None),
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
    target_price = resistance
    return TriggerLevels(
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        target_price=target_price,
        invalidation=f"{symbol} 跌破 {stop_loss:.2f}",
    )


def _format_news_notes(news: dict[str, list[NewsItem]]) -> list[str]:
    """把新闻条目压缩为日报和周报中的市场背景要点。"""
    notes = []
    for symbol, items in news.items():
        if not items:
            continue
        for item in items[:2]:
            title = f"[{item.title}]({item.url})" if item.url else item.title
            notes.append(f"{symbol} 搜索线索（未核验全文）: {title}；来源 {item.source}")
    return notes
