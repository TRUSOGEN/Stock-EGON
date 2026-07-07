"""技术指标计算模块。

本模块只处理已经标准化的日线 DataFrame，输入字段包括 date、open、high、low、close、
volume 和 turnover。它不访问外部网络，因此可以被单元测试稳定覆盖。
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {"date", "open", "high", "low", "close", "volume"}


def require_daily_columns(frame: pd.DataFrame) -> None:
    """检查日线数据是否包含核心字段。"""
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"日线数据缺少必要字段: {', '.join(sorted(missing))}")


def _rsi(series: pd.Series, window: int) -> pd.Series:
    """计算 RSI 指标。"""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=window, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(window=window, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100).clip(0, 100)


def compute_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """计算均线、MACD、RSI、KDJ、布林带、量比等常用技术指标。"""
    require_daily_columns(frame)
    result = frame.copy().sort_values("date").reset_index(drop=True)
    close = result["close"].astype(float)
    high = result["high"].astype(float)
    low = result["low"].astype(float)
    volume = result["volume"].astype(float)

    for window in (5, 10, 20, 60):
        result[f"ma{window}"] = close.rolling(window=window, min_periods=1).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    result["dif"] = ema12 - ema26
    result["dea"] = result["dif"].ewm(span=9, adjust=False).mean()
    result["macd"] = (result["dif"] - result["dea"]) * 2

    for window in (6, 12, 24):
        result[f"rsi{window}"] = _rsi(close, window)

    low_min = low.rolling(window=9, min_periods=1).min()
    high_max = high.rolling(window=9, min_periods=1).max()
    rsv = ((close - low_min) / (high_max - low_min).replace(0, np.nan) * 100).fillna(50)
    result["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
    result["kdj_d"] = result["kdj_k"].ewm(com=2, adjust=False).mean()
    result["kdj_j"] = 3 * result["kdj_k"] - 2 * result["kdj_d"]

    result["boll_mid"] = close.rolling(window=20, min_periods=1).mean()
    boll_std = close.rolling(window=20, min_periods=1).std(ddof=0).fillna(0)
    result["boll_upper"] = result["boll_mid"] + 2 * boll_std
    result["boll_lower"] = result["boll_mid"] - 2 * boll_std

    avg_volume = volume.rolling(window=5, min_periods=1).mean()
    result["volume_ratio"] = (volume / avg_volume.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    result["volume_ratio"] = result["volume_ratio"].fillna(0)
    return result


def latest_cross_signal(series_a: pd.Series, series_b: pd.Series) -> str:
    """识别最近一日是否发生上穿或下穿。"""
    if len(series_a) < 2 or len(series_b) < 2:
        return "none"
    prev_diff = series_a.iloc[-2] - series_b.iloc[-2]
    curr_diff = series_a.iloc[-1] - series_b.iloc[-1]
    if prev_diff <= 0 < curr_diff:
        return "golden"
    if prev_diff >= 0 > curr_diff:
        return "death"
    return "none"


def safe_float(value: object, digits: int = 4) -> float | None:
    """把 pandas/numpy 数值转成 JSON 友好的 float。"""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)
