#!/usr/bin/env python3
"""把已经生成的美股报告 JSON 推送到企业微信群机器人。

脚本读取统一结果 JSON 中的 `data.report_markdown` 字段，并通过
`WECHAT_WEBHOOK_URL` 或 `WECHAT_BOT_WEBHOOK` 发送 Markdown 消息。未配置 webhook
时视为显式跳过，方便同一个 GitHub Actions workflow 同时支持有通知和无通知场景。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a_stock_quant.output import dumps_json, make_error_result, make_result
from us_stock_agent.notifications import send_wechat_markdown


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="推送美股报告到企业微信")
    parser.add_argument("--report-file", required=True, help="日报或周报 JSON 文件路径")
    return parser.parse_args()


def main() -> int:
    """读取报告并推送到微信。"""
    args = parse_args()
    try:
        report = _load_report(Path(args.report_file))
        markdown = _extract_markdown(report)
        send_result = send_wechat_markdown(markdown)
        print(
            dumps_json(
                make_result(
                    module="send_wechat_report",
                    data=send_result,
                    data_time=report.get("data_time"),
                    source_api="enterprise_wechat_webhook",
                    warnings=["企业微信群机器人只支持单向推送，不能接收用户追问。"],
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
                    module="send_wechat_report",
                    error=str(exc),
                    source_api="enterprise_wechat_webhook",
                    warnings=["企业微信群机器人只支持单向推送，不能接收用户追问。"],
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
        raise ValueError("report JSON 的 ok 必须为 true，失败报告不会推送。")
    data = report.get("data")
    if not isinstance(data, dict):
        raise ValueError("report JSON 缺少 data 对象。")
    markdown = data.get("report_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("report JSON 缺少 data.report_markdown。")
    return markdown


if __name__ == "__main__":
    raise SystemExit(main())
