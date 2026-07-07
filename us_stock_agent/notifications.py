"""美股持仓 agent 的外部通知适配层。

本模块只负责把已经生成的 Markdown 报告发送到通知渠道。报告生成、动作评分、
风险判断和数据抓取仍然留在各自的业务模块中，避免通知渠道变化影响分析逻辑。
"""

from __future__ import annotations

import os
from typing import Any, Callable

import requests


PostClient = Callable[..., Any]


def build_wechat_markdown_payload(markdown: str) -> dict[str, Any]:
    """把报告 Markdown 包装为企业微信群机器人消息体。"""
    content = markdown.strip()
    if not content:
        raise ValueError("wechat markdown content 不能为空。")
    return {"msgtype": "markdown", "markdown": {"content": content}}


def send_wechat_markdown(
    markdown: str,
    *,
    webhook_url: str | None = None,
    post: PostClient | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    """发送企业微信 Markdown 消息，并返回可审计的发送结果。

    未配置 webhook 时返回 skipped 结果，不让日报或周报任务失败。配置了 webhook
    但发送失败时返回 `sent=false`，由上层 CLI 决定是否用非零退出码暴露错误。
    """
    url = webhook_url or os.environ.get("WECHAT_WEBHOOK_URL") or os.environ.get("WECHAT_BOT_WEBHOOK")
    if not url:
        return {"sent": False, "skipped": True, "reason": "wechat_webhook_not_configured"}

    client = post or requests.post
    payload = build_wechat_markdown_payload(markdown)
    response = client(url, json=payload, timeout=timeout)
    status_code = getattr(response, "status_code", None)
    response_payload = _read_json_response(response)
    errcode = response_payload.get("errcode", 0) if isinstance(response_payload, dict) else 0
    ok_status = status_code is not None and 200 <= int(status_code) < 300
    ok_business = int(errcode or 0) == 0
    sent = bool(ok_status and ok_business)
    return {
        "sent": sent,
        "skipped": False,
        "reason": None if sent else "wechat_webhook_failed",
        "status_code": status_code,
        "response": response_payload,
    }


def _read_json_response(response: Any) -> dict[str, Any]:
    """读取 webhook 响应 JSON；非 JSON 响应保留为空对象。"""
    try:
        payload = response.json()
    except ValueError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {"payload": payload}
