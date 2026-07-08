"""美股持仓 agent 的外部通知适配层。

本模块只负责把已经生成的 Markdown 报告发送到通知渠道。报告生成、动作评分、
风险判断和数据抓取仍然留在各自的业务模块中，避免通知渠道变化影响分析逻辑。
"""

from __future__ import annotations

import html
import os
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Callable

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - 仅在极简测试环境触发
    requests = None


PostClient = Callable[..., Any]
SMTPFactory = Callable[..., Any]

DEFAULT_INTERACTIVE_CHART_URL = "https://trusogen.github.io/Stock-EGON/stock-chart.html"


@dataclass(frozen=True)
class EmailAttachment:
    """邮件二进制图片资源。"""

    filename: str
    content_type: str
    data: bytes
    content_id: str | None = None


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

    if post is not None:
        client = post
    elif requests is not None:
        client = requests.post
    else:
        raise RuntimeError("当前环境缺少 requests，无法发送企业微信消息。")
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
    attachments: list[EmailAttachment | dict[str, Any]] | None = None,
    interactive_chart_url: str | None = None,
) -> EmailMessage:
    """把报告 Markdown 包装为 text+html 邮件。"""
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
    normalized_attachments = _normalize_attachments(attachments)
    message.set_content(render_email_plain_text(content))
    message.add_alternative(
        render_email_html(
            content,
            inline_images=normalized_attachments,
            interactive_chart_url=interactive_chart_url,
        ),
        subtype="html",
    )
    html_part = message.get_body(preferencelist=("html",))
    for attachment in normalized_attachments:
        maintype, subtype = _split_content_type(attachment.content_type)
        if html_part is None:
            message.add_attachment(
                attachment.data,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.filename,
            )
            continue
        html_part.add_related(
            attachment.data,
            maintype=maintype,
            subtype=subtype,
            cid=f"<{attachment.content_id}>",
            filename=attachment.filename,
            disposition="inline",
        )
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
    attachments: list[EmailAttachment | dict[str, Any]] | None = None,
    interactive_chart_url: str | None = None,
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
    chart_url = interactive_chart_url or os.environ.get("INTERACTIVE_CHART_URL") or DEFAULT_INTERACTIVE_CHART_URL
    if not host or not from_addr or not to_addrs:
        return {"sent": False, "skipped": True, "reason": "email_not_configured"}
    if login_user and not login_password:
        return {"sent": False, "skipped": False, "reason": "email_smtp_auth_incomplete"}

    message = build_email_message(
        markdown,
        subject=subject,
        sender=from_addr,
        recipients=to_addrs,
        attachments=attachments,
        interactive_chart_url=chart_url,
    )
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
        "inline_image_filenames": [item.filename for item in _normalize_attachments(attachments)],
    }


def render_email_plain_text(markdown: str) -> str:
    """把 Markdown 报告转换成更适合普通邮件客户端的纯文本。"""
    lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if lines and lines[-1] != "":
                lines.append("")
            continue
        normalized = _strip_inline_markdown(_strip_heading_marker(line))
        if line.lstrip().startswith("- "):
            normalized = f"- {_strip_inline_markdown(line.lstrip()[2:])}"
        if normalized:
            lines.append(normalized)
    return "\n".join(_squash_blank_lines(lines)).strip()


def render_email_html(
    markdown: str,
    *,
    inline_images: list[EmailAttachment] | None = None,
    interactive_chart_url: str | None = None,
) -> str:
    """把 Markdown 报告转换成简单、稳定的 HTML 邮件正文。"""
    parts = [
        "<html><body style=\"font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1f2933; line-height: 1.6;\">"
    ]
    images_by_symbol = _group_images_by_symbol(inline_images or [])
    inserted_image_ids: set[int] = set()
    current_symbol: str | None = None
    pending_list: list[str] = []

    def flush_pending_list() -> None:
        """把暂存的 Markdown 列表落到 HTML。"""
        nonlocal pending_list
        if not pending_list:
            return
        parts.append("<ul>")
        parts.extend(f"<li>{item}</li>" for item in pending_list)
        parts.append("</ul>")
        pending_list = []

    def insert_current_symbol_images() -> None:
        """在当前股票小节结束时插入对应报价图。"""
        if current_symbol is None:
            return
        for image in images_by_symbol.get(current_symbol, []):
            if id(image) in inserted_image_ids:
                continue
            parts.append(_render_inline_image_html(image, interactive_chart_url=interactive_chart_url))
            inserted_image_ids.add(id(image))

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            flush_pending_list()
            continue
        if line.startswith("- "):
            pending_list.append(_render_inline_html(line[2:]))
            continue
        flush_pending_list()
        if line.startswith(("# ", "## ", "### ")):
            insert_current_symbol_images()
            current_symbol = _symbol_from_heading(line[4:]) if line.startswith("### ") else None
        if line.startswith("### "):
            parts.append(f"<h3>{_render_inline_html(line[4:])}</h3>")
        elif line.startswith("## "):
            parts.append(f"<h2>{_render_inline_html(line[3:])}</h2>")
        elif line.startswith("# "):
            parts.append(f"<h1>{_render_inline_html(line[2:])}</h1>")
        else:
            parts.append(f"<p>{_render_inline_html(line)}</p>")
    flush_pending_list()
    insert_current_symbol_images()
    if inline_images:
        unmatched_images = [image for image in inline_images if id(image) not in inserted_image_ids]
        if unmatched_images:
            parts.append("<h2>报价图</h2>")
            for image in unmatched_images:
                parts.append(_render_inline_image_html(image, interactive_chart_url=interactive_chart_url))
    parts.append("</body></html>")
    return "".join(parts)


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


def _normalize_attachments(
    attachments: list[EmailAttachment | dict[str, Any]] | None,
) -> list[EmailAttachment]:
    """把调用方提供的图片资源规范化为 dataclass。"""
    normalized: list[EmailAttachment] = []
    for item in attachments or []:
        if isinstance(item, EmailAttachment):
            normalized.append(item)
            continue
        normalized.append(
            EmailAttachment(
                filename=str(item["filename"]),
                content_type=str(item["content_type"]),
                data=bytes(item["data"]),
                content_id=str(item.get("content_id") or _content_id_for_filename(str(item["filename"]))),
            )
        )
    return [
        item
        if item.content_id
        else EmailAttachment(
            filename=item.filename,
            content_type=item.content_type,
            data=item.data,
            content_id=_content_id_for_filename(item.filename),
        )
        for item in normalized
    ]


def _content_id_for_filename(filename: str) -> str:
    """根据文件名生成稳定的 Content-ID。"""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", filename).strip("-") or "chart"
    return f"{safe}@stock-egon"


def _group_images_by_symbol(images: list[EmailAttachment]) -> dict[str, list[EmailAttachment]]:
    """按图片文件名前缀提取 ticker 并分组。"""
    grouped: dict[str, list[EmailAttachment]] = {}
    for image in images:
        symbol = _symbol_from_filename(image.filename)
        if symbol is None:
            continue
        grouped.setdefault(symbol, []).append(image)
    return grouped


def _symbol_from_filename(filename: str) -> str | None:
    """从 `SPEX-price-volume.png` 一类文件名中提取 ticker。"""
    match = re.match(r"^([A-Za-z][A-Za-z0-9.]*)", filename)
    if not match:
        return None
    return match.group(1).upper()


def _symbol_from_heading(value: str) -> str | None:
    """从股票小节标题中提取 ticker。"""
    text = _strip_inline_markdown(value).strip()
    match = re.match(r"^([A-Za-z][A-Za-z0-9.]*)\b", text)
    if not match:
        return None
    return match.group(1).upper()


def _render_inline_image_html(image: EmailAttachment, *, interactive_chart_url: str | None = None) -> str:
    """渲染邮件正文内嵌图片。"""
    alt_text = html.escape(image.filename)
    content_id = html.escape(image.content_id or image.filename, quote=True)
    symbol = _symbol_from_filename(image.filename)
    link = _interactive_chart_link(interactive_chart_url, symbol)
    link_html = (
        f'<div style="margin-top: 8px;"><a href="{html.escape(link, quote=True)}" '
        'style="color: #1f67b2; font-size: 14px; text-decoration: none;">打开交互图</a></div>'
        if link
        else ""
    )
    return (
        '<figure style="margin: 16px 0 22px 0;">'
        f'<img src="cid:{content_id}" alt="{alt_text}" '
        'style="max-width: 100%; height: auto; border: 1px solid #d7e3ee; border-radius: 8px;" />'
        f'<figcaption style="color: #5e6875; font-size: 13px;">{alt_text}</figcaption>'
        f"{link_html}"
        "</figure>"
    )


def _interactive_chart_link(base_url: str | None, symbol: str | None) -> str | None:
    """拼出单票交互图链接。"""
    if not base_url or not symbol:
        return None
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}symbol={html.escape(symbol, quote=True)}"


def _split_content_type(value: str) -> tuple[str, str]:
    """拆分 MIME content type。"""
    if "/" not in value:
        return "application", "octet-stream"
    maintype, subtype = value.split("/", 1)
    return maintype, subtype


def _strip_heading_marker(value: str) -> str:
    """移除 Markdown 标题前缀。"""
    stripped = value.lstrip()
    for prefix in ("### ", "## ", "# "):
        if stripped.startswith(prefix):
            return stripped[len(prefix) :]
    return stripped


def _strip_inline_markdown(value: str) -> str:
    """移除少量常见 Markdown 语法，让纯文本更干净。"""
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", value)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", text)
    return text.strip()


def _render_inline_html(value: str) -> str:
    """把行内 Markdown 近似转换为 HTML。"""
    raw = _strip_inline_markdown(value)
    escaped = html.escape(raw)
    escaped = re.sub(
        r"([A-Za-z][A-Za-z0-9+.-]*://[^\s)]+)",
        lambda match: f'<a href="{html.escape(match.group(1), quote=True)}">{html.escape(match.group(1))}</a>',
        escaped,
    )
    return escaped


def _squash_blank_lines(lines: list[str]) -> list[str]:
    """压缩连续空行。"""
    squashed: list[str] = []
    for line in lines:
        if line == "" and squashed and squashed[-1] == "":
            continue
        squashed.append(line)
    return squashed


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
