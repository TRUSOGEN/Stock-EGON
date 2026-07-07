#!/usr/bin/env python3
"""把已经生成的美股报告 JSON 通过 SMTP 邮件发送。

脚本读取统一结果 JSON 中的 `data.report_markdown` 字段，并通过
`EMAIL_ADDRESS`、`EMAIL_AUTH_CODE` 发送 QQ 邮箱纯文本邮件。其他邮箱可继续使用
`EMAIL_SMTP_HOST`、`EMAIL_USERNAME`、`EMAIL_PASSWORD`、`EMAIL_FROM`、`EMAIL_TO`
等完整 SMTP 环境变量。未配置 SMTP 时显式跳过，避免影响日报和周报生成。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a_stock_quant.output import dumps_json, make_error_result, make_result
from us_stock_agent.notifications import send_email_markdown


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="通过 SMTP 邮件发送美股报告")
    parser.add_argument("--report-file", required=True, help="日报或周报 JSON 文件路径")
    parser.add_argument("--subject", help="邮件标题；默认根据报告类型生成")
    return parser.parse_args()


def main() -> int:
    """读取报告并发送邮件。"""
    args = parse_args()
    try:
        report = _load_report(Path(args.report_file))
        markdown = _extract_markdown(report)
        send_result = send_email_markdown(markdown, subject=args.subject or _default_subject(report))
        print(
            dumps_json(
                make_result(
                    module="send_email_report",
                    data=send_result,
                    data_time=report.get("data_time"),
                    source_api="smtp_email",
                    warnings=["邮件报告是研究辅助，不构成投资建议或交易指令。"],
                )
            )
        )
        if send_result.get("skipped"):
            return 0
        return 0 if send_result.get("sent") else 2
    except Exception as exc:  # noqa: BLE001
        print(
            dumps_json(
                make_error_result(
                    module="send_email_report",
                    error=str(exc),
                    source_api="smtp_email",
                    warnings=["邮件报告是研究辅助，不构成投资建议或交易指令。"],
                )
            )
        )
        return 2


def _load_report(path: Path) -> dict[str, Any]:
    """从磁盘读取统一报告 JSON。"""
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("report JSON 顶层必须是对象。")
    return payload


def _extract_markdown(report: dict[str, Any]) -> str:
    """从统一结果 JSON 中提取 Markdown 报告正文。"""
    if report.get("ok") is not True:
        raise ValueError("report JSON 的 ok 必须为 true，失败报告不会发送。")
    data = report.get("data")
    if not isinstance(data, dict):
        raise ValueError("report JSON 缺少 data 对象。")
    markdown = data.get("report_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("report JSON 缺少 data.report_markdown。")
    return markdown


def _default_subject(report: dict[str, Any]) -> str:
    """根据报告类型生成默认邮件标题。"""
    module = str(report.get("module") or "")
    if "weekly" in module:
        return "Stock-EGON 每周美股持仓复盘"
    return "Stock-EGON 每日美股持仓简报"


if __name__ == "__main__":
    raise SystemExit(main())
