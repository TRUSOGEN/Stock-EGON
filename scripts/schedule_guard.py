#!/usr/bin/env python3
"""为 GitHub Actions 定时补跑生成去重判断。

脚本在 workflow 开始时运行：普通手动触发时直接放行；定时触发和带去重标记的
外部补发会读取仓库最近的 artifact 名称，若当天同类型报告已经上传过成功 marker，
则输出 skip=true。它只访问 GitHub Actions metadata，不读取持仓、行情、邮件或
LLM secret。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from us_stock_agent.schedule_guard import ScheduleGuardError, build_guard_decision


def main() -> int:
    """执行 schedule guard 并写入 GitHub Actions outputs。"""
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    schedule = os.environ.get("GITHUB_EVENT_SCHEDULE", "").strip()
    report_type = os.environ.get("WORKFLOW_REPORT_TYPE", "daily").strip()
    manual_deduplication = _parse_bool(os.environ.get("WORKFLOW_DEDUPE_MANUAL", "false"))
    now_iso = _utc_now_iso()
    artifact_names = _fetch_artifact_names_for_event(
        event_name=event_name,
        manual_deduplication=manual_deduplication,
    )

    decision = build_guard_decision(
        event_name=event_name,
        schedule=schedule,
        report_type=report_type,
        manual_deduplication=manual_deduplication,
        now_iso=now_iso,
        artifact_names=artifact_names,
    )
    outputs = {
        "skip": "true" if decision.skip else "false",
        "report_type": decision.report_type,
        "marker": decision.marker,
        "reason": decision.reason,
    }
    _write_outputs(outputs)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    return 0


def _utc_now_iso() -> str:
    """返回 GitHub runner 当前 UTC 时间，格式与 GitHub API 时间一致。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fetch_artifact_names_for_event(*, event_name: str, manual_deduplication: bool) -> list[str]:
    """在自动调度或外部去重补发时读取仓库 artifact 名称。"""
    if event_name != "schedule" and not manual_deduplication:
        return []
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token:
        raise ScheduleGuardError("schedule guard 缺少 GITHUB_TOKEN，无法读取 marker artifacts。")
    if not repo:
        raise ScheduleGuardError("schedule guard 缺少 GITHUB_REPOSITORY，无法读取 marker artifacts。")
    return _fetch_artifact_names(repo=repo, token=token)


def _parse_bool(value: str) -> bool:
    """解析 GitHub Actions 输入的布尔字符串。"""
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off", ""}:
        return False
    raise ScheduleGuardError(f"无法解析布尔值: {value}")


def _fetch_artifact_names(*, repo: str, token: str) -> list[str]:
    """通过 GitHub API 读取未过期 artifact 名称。"""
    names: list[str] = []
    for page in range(1, 11):
        url = f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100&page={page}"
        payload = _github_api_json(url=url, token=token)
        artifacts = payload.get("artifacts", [])
        if not isinstance(artifacts, list):
            raise ScheduleGuardError("GitHub artifacts API 返回结构异常。")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            if artifact.get("expired"):
                continue
            name = artifact.get("name")
            if isinstance(name, str):
                names.append(name)
        if len(artifacts) < 100:
            break
    return names


def _github_api_json(*, url: str, token: str) -> dict[str, Any]:
    """读取 GitHub API JSON 响应。"""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "stock-egon-schedule-guard",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ScheduleGuardError("GitHub API 返回的 JSON 不是对象。")
    return data


def _write_outputs(outputs: dict[str, str]) -> None:
    """把判断结果写入 GitHub Actions output 文件。"""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as output_file:
        for key, value in outputs.items():
            clean_value = value.replace("\n", " ")
            output_file.write(f"{key}={clean_value}\n")


if __name__ == "__main__":
    raise SystemExit(main())
