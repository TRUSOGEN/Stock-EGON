"""数据质量归一化与评估。

参考项目把数据质量作为动作 guardrail 的前置条件。本模块保留同样的思想：质量等级只来自
显式输入或可验证的数据完整性，不用主观猜测美化结果。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable, Literal

import pandas as pd

DataQuality = Literal["high", "medium", "low", "poor", "unknown"]


_QUALITY_ALIASES: dict[str, DataQuality] = {
    "high": "high",
    "good": "high",
    "medium": "medium",
    "usable": "medium",
    "ok": "medium",
    "fair": "medium",
    "low": "low",
    "limited": "low",
    "partial": "low",
    "degraded": "low",
    "stale": "low",
    "fallback": "low",
    "poor": "poor",
    "missing": "poor",
    "unavailable": "poor",
    "fetch_failed": "poor",
    "not_supported": "poor",
    "unknown": "unknown",
}

_QUALITY_SEVERITY: dict[DataQuality, int] = {
    "unknown": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "poor": 4,
}


def normalize_data_quality(value: Any) -> DataQuality:
    """从标量或嵌套结构里取显式最差质量等级。"""
    known_levels = [level for level in _explicit_quality_levels(value) if level != "unknown"]
    if not known_levels:
        return "unknown"
    return max(known_levels, key=lambda level: _QUALITY_SEVERITY[level])


def assess_history_quality(history: pd.DataFrame, *, min_rows: int = 60) -> DataQuality:
    """根据历史行情完整性评估质量。"""
    if history is None or history.empty:
        return "poor"
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(history.columns):
        return "poor"
    if len(history) < max(20, min_rows // 2):
        return "low"
    if len(history) < min_rows:
        return "medium"
    if history[list(required)].isna().any().any():
        return "low"
    return "high"


def _normalize_scalar(value: Any) -> DataQuality:
    """归一化单个质量值。"""
    if value is None:
        return "unknown"
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return "unknown"
        return _QUALITY_ALIASES.get(text, "unknown")
    return "unknown"


def _explicit_quality_levels(value: Any) -> Iterable[DataQuality]:
    """递归提取显式质量等级。"""
    scalar = _normalize_scalar(value)
    if scalar != "unknown":
        yield scalar
        return
    if not isinstance(value, Mapping):
        yield "unknown"
        return
    for key in ("level", "quality_level", "status", "data_quality", "quality"):
        if key in value:
            yield from _explicit_quality_levels(value.get(key))
    for key in ("quote", "daily_bars", "technical", "news", "fundamental"):
        if key in value:
            yield from _explicit_quality_levels(value.get(key))
