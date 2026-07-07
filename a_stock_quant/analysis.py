"""选股、个股诊断和市场概览的业务分析逻辑。

这里的函数接收已经抓取并标准化的数据，输出稳定的字典结构。外部数据源字段如何变化
由 data_provider 处理，本模块专注于因子、信号和评分。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .indicators import compute_indicators, latest_cross_signal, safe_float


def _bounded_score(value: float) -> float:
    """把分数限制在 0 到 100。"""
    return round(max(0.0, min(100.0, value)), 2)


def _technical_score(indicators: pd.DataFrame) -> tuple[float, list[str]]:
    """根据均线、MACD、RSI、KDJ、布林带和成交量生成技术分。"""
    latest = indicators.iloc[-1]
    score = 50.0
    reasons: list[str] = []

    if latest["ma5"] > latest["ma10"] > latest["ma20"]:
        score += 16
        reasons.append("短中期均线多头排列")
    elif latest["ma5"] < latest["ma10"] < latest["ma20"]:
        score -= 16
        reasons.append("短中期均线空头排列")

    macd_cross = latest_cross_signal(indicators["dif"], indicators["dea"])
    if latest["macd"] > 0:
        score += 10
        reasons.append("MACD 柱线为正")
    if macd_cross == "golden":
        score += 8
        reasons.append("MACD 近期上穿")
    elif macd_cross == "death":
        score -= 8
        reasons.append("MACD 近期下穿")

    if 45 <= latest["rsi6"] <= 75:
        score += 8
        reasons.append("RSI 处于偏强但未极端区间")
    elif latest["rsi6"] > 85:
        score -= 8
        reasons.append("RSI 短线过热")
    elif latest["rsi6"] < 25:
        score -= 4
        reasons.append("RSI 短线弱势")

    if latest["close"] > latest["boll_mid"]:
        score += 6
        reasons.append("价格位于布林中轨上方")
    if latest["volume_ratio"] > 1.2 and latest["close"] >= indicators["close"].iloc[-2]:
        score += 8
        reasons.append("上涨伴随成交量放大")
    elif latest["volume_ratio"] < 0.7:
        score -= 4
        reasons.append("成交量低于近期均量")

    return _bounded_score(score), reasons


def _fundamental_score(pe: float | None, pb: float | None, turnover: float | None) -> tuple[float, list[str]]:
    """根据 PE、PB、换手率生成基础面/交易活跃度分。"""
    score = 50.0
    reasons: list[str] = []
    if pe is not None:
        if 0 < pe <= 35:
            score += 18
            reasons.append("PE 位于可解释区间")
        elif pe > 80 or pe <= 0:
            score -= 12
            reasons.append("PE 估值或盈利口径风险较高")
    if pb is not None:
        if 0 < pb <= 5:
            score += 14
            reasons.append("PB 未处于极端高位")
        elif pb > 10 or pb <= 0:
            score -= 10
            reasons.append("PB 估值或净资产口径风险较高")
    if turnover is not None:
        if 0.5 <= turnover <= 8:
            score += 10
            reasons.append("换手率处于较健康区间")
        elif turnover > 15:
            score -= 8
            reasons.append("换手率过高，短线波动风险较大")
    return _bounded_score(score), reasons


def analyze_stock(code: str, name: str, history: pd.DataFrame) -> dict[str, Any]:
    """对单只股票生成技术诊断。"""
    indicators = compute_indicators(history)
    latest = indicators.iloc[-1]
    tech_score, reasons = _technical_score(indicators)

    if tech_score >= 68:
        trend = "偏多"
        signal = "偏多"
    elif tech_score <= 42:
        trend = "偏空"
        signal = "偏空"
    else:
        trend = "震荡"
        signal = "中性"

    recent = indicators.tail(min(20, len(indicators)))
    support = safe_float(recent["low"].min(), 3)
    resistance = safe_float(recent["high"].max(), 3)
    return {
        "code": code,
        "name": name,
        "score": tech_score,
        "trend": trend,
        "signal": signal,
        "latest": {
            "date": str(latest["date"])[:10],
            "close": safe_float(latest["close"], 3),
            "change_pct": safe_float(latest.get("change_pct"), 3),
            "volume": safe_float(latest["volume"], 0),
        },
        "indicators": {
            "ma5": safe_float(latest["ma5"], 3),
            "ma10": safe_float(latest["ma10"], 3),
            "ma20": safe_float(latest["ma20"], 3),
            "ma60": safe_float(latest["ma60"], 3),
            "dif": safe_float(latest["dif"], 4),
            "dea": safe_float(latest["dea"], 4),
            "macd": safe_float(latest["macd"], 4),
            "rsi6": safe_float(latest["rsi6"], 2),
            "rsi12": safe_float(latest["rsi12"], 2),
            "kdj_k": safe_float(latest["kdj_k"], 2),
            "kdj_d": safe_float(latest["kdj_d"], 2),
            "kdj_j": safe_float(latest["kdj_j"], 2),
            "boll_upper": safe_float(latest["boll_upper"], 3),
            "boll_mid": safe_float(latest["boll_mid"], 3),
            "boll_lower": safe_float(latest["boll_lower"], 3),
            "volume_ratio": safe_float(latest["volume_ratio"], 3),
        },
        "key_levels": {"support": support, "resistance": resistance},
        "observations": reasons,
        "risk_note": "仅为技术信号与观察点，不构成买卖建议。",
    }


def screen_stocks(
    candidates: list[dict[str, Any]],
    *,
    top: int,
    strategy: str,
    min_price: float,
    max_price: float | None = None,
    min_volume: float = 5000,
) -> dict[str, Any]:
    """对候选股票进行技术、基础面或综合策略排序。"""
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        indicators = compute_indicators(candidate["history"])
        latest = indicators.iloc[-1]
        price = float(latest["close"])
        volume = float(latest["volume"])
        if price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue
        if volume < min_volume:
            continue

        tech_score, tech_reasons = _technical_score(indicators)
        turnover = safe_float(latest.get("turnover"), 4)
        fund_score, fund_reasons = _fundamental_score(
            safe_float(candidate.get("pe"), 4),
            safe_float(candidate.get("pb"), 4),
            turnover,
        )
        if strategy == "technical":
            score = tech_score
            reasons = tech_reasons
        elif strategy == "fundamental":
            score = fund_score
            reasons = fund_reasons
        elif strategy == "multi_factor":
            score = _bounded_score(tech_score * 0.65 + fund_score * 0.35)
            reasons = tech_reasons[:3] + fund_reasons[:3]
        else:
            raise ValueError("strategy 必须是 technical、fundamental 或 multi_factor")

        if score >= 70:
            signal = "强势"
        elif score >= 50:
            signal = "中性"
        else:
            signal = "弱势"
        results.append(
            {
                "code": candidate["code"],
                "name": candidate.get("name") or candidate["code"],
                "score": score,
                "price": safe_float(price, 3),
                "change_pct": safe_float(latest.get("change_pct"), 3),
                "pe": safe_float(candidate.get("pe"), 3),
                "pb": safe_float(candidate.get("pb"), 3),
                "volume": safe_float(volume, 0),
                "volume_ratio": safe_float(latest["volume_ratio"], 3),
                "signal": signal,
                "observations": reasons,
            }
        )

    ranked = sorted(results, key=lambda item: item["score"], reverse=True)[:top]
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return {"strategy": strategy, "count": len(ranked), "results": ranked}


def summarize_market(
    *,
    indices: list[dict[str, Any]],
    breadth: dict[str, Any],
    boards: list[dict[str, Any]],
    hot_stocks: list[dict[str, Any]],
) -> dict[str, Any]:
    """整理大盘、市场广度、板块轮动和热门个股摘要。"""
    return {
        "indices": indices,
        "breadth": breadth,
        "leading_boards": boards[:10],
        "hot_stocks": hot_stocks[:10],
        "risk_note": "板块和热门个股仅反映当前可获取数据的排序，不代表后续表现。",
    }
