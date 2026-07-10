"""GitHub Actions 定时报告的补跑去重逻辑。

本模块只处理 GitHub Actions 触发前的轻量判断：把 cron 表达式或手动输入映射到
日报/周报，并基于当天已存在的 marker artifact 决定是否跳过自动补跑。核心报告
生成仍由 runner 和邮件脚本负责，本模块不访问行情、新闻或邮件服务。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

DAILY_SCHEDULES = ("17 0 * * 2-6", "37 0 * * 2-6", "57 0 * * 2-6")
WEEKLY_SCHEDULES = ("17 1 * * 6", "37 1 * * 6", "57 1 * * 6")
SUPPORTED_REPORT_TYPES = ("daily", "weekly")


class ScheduleGuardError(RuntimeError):
    """定时触发配置无法被安全识别。"""


@dataclass(frozen=True)
class GuardDecision:
    """一次定时触发的去重判断结果。"""

    report_type: str
    marker: str
    skip: bool
    reason: str


def report_type_for_schedule(schedule: str) -> str:
    """把 GitHub Actions cron 表达式映射为报告类型。"""
    normalized = schedule.strip()
    if normalized in DAILY_SCHEDULES:
        return "daily"
    if normalized in WEEKLY_SCHEDULES:
        return "weekly"
    raise ScheduleGuardError(f"未知的定时表达式: {schedule}")


def normalize_report_type(value: str) -> str:
    """校验并标准化手动触发输入中的报告类型。"""
    normalized = value.strip().lower()
    if normalized in SUPPORTED_REPORT_TYPES:
        return normalized
    raise ScheduleGuardError(f"未知的报告类型: {value}")


def marker_name(report_type: str, now_iso: str) -> str:
    """生成某个报告类型在北京时间当天的 marker artifact 名称。"""
    normalized_type = normalize_report_type(report_type)
    normalized_iso = now_iso.strip()
    if normalized_iso.endswith("Z"):
        normalized_iso = f"{normalized_iso[:-1]}+00:00"
    try:
        timestamp = datetime.fromisoformat(normalized_iso)
    except ValueError as exc:
        raise ScheduleGuardError(f"无法解析当前时间: {now_iso}") from exc
    if timestamp.tzinfo is None:
        raise ScheduleGuardError(f"当前时间缺少时区: {now_iso}")
    beijing_date = timestamp.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    return f"us-stock-report-marker-{normalized_type}-{beijing_date}"


def build_guard_decision(
    *,
    event_name: str,
    schedule: str = "",
    report_type: str = "",
    now_iso: str,
    artifact_names: list[str],
) -> GuardDecision:
    """基于事件上下文和已有 artifacts 构建去重判断。"""
    if event_name == "schedule":
        resolved_type = report_type_for_schedule(schedule)
        marker = marker_name(resolved_type, now_iso)
        if marker in set(artifact_names):
            return GuardDecision(
                report_type=resolved_type,
                marker=marker,
                skip=True,
                reason=f"当天已有成功 marker: {marker}",
            )
        return GuardDecision(
            report_type=resolved_type,
            marker=marker,
            skip=False,
            reason=f"未发现当天成功 marker: {marker}",
        )
    if event_name == "workflow_dispatch":
        resolved_type = normalize_report_type(report_type or "daily")
        return GuardDecision(
            report_type=resolved_type,
            marker=marker_name(resolved_type, now_iso),
            skip=False,
            reason="手动触发不做去重跳过。",
        )
    raise ScheduleGuardError(f"不支持的触发事件: {event_name}")
