"""经典技术策略回测模块。

回测采用下一交易日开盘价成交、全仓进出、无融资融券的简化规则。手续费和滑点作为
显式参数进入成本计算，避免把策略信号直接等同于可实现收益。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .indicators import compute_indicators, require_daily_columns, safe_float


def _strategy_signals(indicators: pd.DataFrame, strategy: str) -> pd.Series:
    """为指定策略生成 1/0 持仓信号。"""
    close = indicators["close"]
    if strategy == "ma_cross":
        return (indicators["ma5"] > indicators["ma20"]).astype(int)
    if strategy == "macd":
        return (indicators["dif"] > indicators["dea"]).astype(int)
    if strategy == "rsi":
        signal = pd.Series(0, index=indicators.index)
        signal[indicators["rsi6"] < 30] = 1
        signal[indicators["rsi6"] > 70] = 0
        return signal.replace(0, np.nan).ffill().fillna(0).astype(int)
    if strategy == "bollinger":
        signal = pd.Series(0, index=indicators.index)
        signal[close < indicators["boll_lower"]] = 1
        signal[close > indicators["boll_upper"]] = 0
        return signal.replace(0, np.nan).ffill().fillna(0).astype(int)
    raise ValueError("strategy 必须是 ma_cross、macd、rsi 或 bollinger")


def _max_drawdown(equity: pd.Series) -> float:
    """计算最大回撤。"""
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    return abs(float(drawdown.min()))


def _sharpe(daily_returns: pd.Series, risk_free_rate: float) -> float | None:
    """计算年化夏普比率。"""
    excess_daily = daily_returns - risk_free_rate / 252
    std = excess_daily.std(ddof=0)
    if std == 0 or np.isnan(std):
        return None
    return float(excess_daily.mean() / std * np.sqrt(252))


def run_backtest(
    history: pd.DataFrame,
    *,
    strategy: str,
    initial_cash: float = 100000,
    commission: float = 0.0003,
    slippage: float = 0.0005,
    risk_free_rate: float = 0.03,
) -> dict[str, Any]:
    """运行单股经典策略回测。"""
    require_daily_columns(history)
    indicators = compute_indicators(history)
    signals = _strategy_signals(indicators, strategy)
    execution_position = signals.shift(1).fillna(0)
    returns = indicators["close"].pct_change().fillna(0)
    trade_flags = execution_position.diff().abs().fillna(execution_position)
    cost = trade_flags * (commission + slippage)
    strategy_returns = execution_position * returns - cost
    equity = initial_cash * (1 + strategy_returns).cumprod()

    completed_trades = int(trade_flags.sum())
    trade_returns = strategy_returns[trade_flags > 0]
    win_rate = float((trade_returns > 0).mean()) if len(trade_returns) else 0.0
    total_return = float(equity.iloc[-1] / initial_cash - 1)
    years = max(len(indicators) / 252, 1 / 252)
    annual_return = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1

    return {
        "strategy": strategy,
        "assumptions": {
            "execution": "信号生成后的下一交易日按收盘收益近似成交",
            "position": "全仓或空仓，不使用杠杆",
            "commission": commission,
            "slippage": slippage,
            "risk_free_rate": risk_free_rate,
            "adjustment": "由数据抓取层决定，默认前复权 qfq",
        },
        "period": {
            "start": str(indicators["date"].iloc[0])[:10],
            "end": str(indicators["date"].iloc[-1])[:10],
            "days": int(len(indicators)),
        },
        "metrics": {
            "total_return": safe_float(total_return, 4),
            "annual_return": safe_float(annual_return, 4),
            "max_drawdown": safe_float(_max_drawdown(equity), 4),
            "win_rate": safe_float(win_rate, 4),
            "sharpe": safe_float(_sharpe(strategy_returns, risk_free_rate), 4),
            "trade_count": completed_trades,
            "ending_equity": safe_float(equity.iloc[-1], 2),
        },
    }
