"""统一 JSON 输出工具。

所有 CLI 都通过本模块生成结果骨架，确保数据时间、抓取时间、来源接口、warning 和
error 的字段稳定存在。这样上层报告、日报或 Codex skill 可以稳定解析，而不会被某个
脚本的临时字段破坏。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


RESEARCH_WARNING = "AKShare 数据来自公开数据源，仅供研究参考，不构成投资建议。"


def _iso_timestamp(value: datetime | None = None) -> str:
    """返回带时区信息的 ISO 时间戳。"""
    timestamp = value or datetime.now(timezone.utc).astimezone()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc).astimezone()
    return timestamp.isoformat(timespec="seconds")


def make_result(
    *,
    module: str,
    data: Any,
    data_time: str | None,
    source_api: str,
    warnings: list[str] | None = None,
    fetched_at: datetime | None = None,
) -> dict[str, Any]:
    """生成成功结果。"""
    result_warnings = list(warnings) if warnings is not None else [RESEARCH_WARNING]
    return {
        "ok": True,
        "module": module,
        "fetched_at": _iso_timestamp(fetched_at),
        "data_time": data_time,
        "source_api": source_api,
        "warnings": result_warnings,
        "errors": [],
        "data": data,
    }


def make_error_result(
    *,
    module: str,
    error: str,
    source_api: str | None = None,
    warnings: list[str] | None = None,
    fetched_at: datetime | None = None,
) -> dict[str, Any]:
    """生成失败结果。"""
    result_warnings = list(warnings) if warnings is not None else [RESEARCH_WARNING]
    return {
        "ok": False,
        "module": module,
        "fetched_at": _iso_timestamp(fetched_at),
        "data_time": None,
        "source_api": source_api,
        "warnings": result_warnings,
        "errors": [error],
        "data": None,
    }


def dumps_json(payload: dict[str, Any]) -> str:
    """把结果序列化为稳定、可读、保留中文的 JSON 字符串。"""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)


def print_json(payload: dict[str, Any]) -> None:
    """向 stdout 打印 JSON 结果。"""
    sys.stdout.write(dumps_json(payload))
    sys.stdout.write("\n")
