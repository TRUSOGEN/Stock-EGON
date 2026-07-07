"""美股持仓 agent 的外部通知适配层。

本模块只负责把已经生成的 Markdown 报告发送到通知渠道。报告生成、动作评分、
风险判断和数据抓取仍然留在各自的业务模块中，避免通知渠道变化影响分析逻辑。
"""

from __future__ import annotations

import smtplib
import os
from email.message import EmailMessage
from typing import Any, Callable

import requests


PostClient = Callable[..., Any]
SMTPFactory = Callable[..., Any]


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


def build_email_message(
    markdown: str,
    *,
    subject: str,
    sender: str,
    recipients: str | list[str],
) -> EmailMessage:
    """把报告 Markdown 包装为纯文本邮件。"""
    content = markdown.strip()
    if not content:
        raise ValueError("email markdown content 不能为空。")
    recipient_list = _normalize_recipients(recipients)
    if not recipient_list:
        raise ValueError("email recipients 不能为空。")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipient_list)
    message.set_content(content)
    return message


def send_email_markdown(
    markdown: str,
    *,
    subject: str = "Stock-EGON 美股持仓报告",
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    sender: str | None = None,
    recipients: str | list[str] | None = None,
    use_tls: bool | None = None,
    timeout: int = 10,
    smtp_factory: SMTPFactory | None = None,
) -> dict[str, Any]:
    """通过 SMTP 发送 Markdown 报告，并返回可审计的发送结果。"""
    shortcut_email = os.environ.get("EMAIL_ADDRESS")
    shortcut_auth_code = os.environ.get("EMAIL_AUTH_CODE")
    inferred_host = "smtp.qq.com" if _is_qq_email(shortcut_email) else None
    host = smtp_host or os.environ.get("EMAIL_SMTP_HOST") or inferred_host
    raw_port = smtp_port or _parse_int(os.environ.get("EMAIL_SMTP_PORT"), default=587)
    login_user = username if username is not None else os.environ.get("EMAIL_USERNAME") or shortcut_email
    login_password = password if password is not None else os.environ.get("EMAIL_PASSWORD") or shortcut_auth_code
    from_addr = sender or os.environ.get("EMAIL_FROM") or login_user
    to_addrs = recipients if recipients is not None else os.environ.get("EMAIL_TO") or shortcut_email
    tls_enabled = use_tls if use_tls is not None else _parse_bool(os.environ.get("EMAIL_USE_TLS"), default=True)
    if not host or not from_addr or not to_addrs:
        return {"sent": False, "skipped": True, "reason": "email_not_configured"}
    if login_user and not login_password:
        return {"sent": False, "skipped": False, "reason": "email_smtp_auth_incomplete"}

    message = build_email_message(markdown, subject=subject, sender=from_addr, recipients=to_addrs)
    factory = smtp_factory or smtplib.SMTP
    smtp = factory(host, raw_port, timeout=timeout)
    try:
        if tls_enabled:
            smtp.starttls()
        if login_user and login_password:
            smtp.login(login_user, login_password)
        smtp.send_message(message)
    finally:
        _close_smtp(smtp)
    return {
        "sent": True,
        "skipped": False,
        "reason": None,
        "smtp_host": host,
        "smtp_port": raw_port,
        "recipients": _normalize_recipients(to_addrs),
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


def _normalize_recipients(recipients: str | list[str]) -> list[str]:
    """解析邮件收件人列表。"""
    if isinstance(recipients, str):
        return [item.strip() for item in recipients.split(",") if item.strip()]
    return [item.strip() for item in recipients if item.strip()]


def _parse_bool(value: str | None, *, default: bool) -> bool:
    """解析布尔环境变量。"""
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(value: str | None, *, default: int) -> int:
    """解析整数环境变量。"""
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _is_qq_email(value: str | None) -> bool:
    """判断邮箱是否可以使用 QQ 邮箱默认 SMTP 配置。"""
    if not value:
        return False
    return value.strip().lower().endswith("@qq.com")


def _close_smtp(smtp: Any) -> None:
    """关闭 SMTP 连接，兼容测试 fake client。"""
    close = getattr(smtp, "quit", None) or getattr(smtp, "close", None)
    if close:
        close()
