"""微信通知层的单元测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from us_stock_agent.notifications import (
    build_email_message,
    build_wechat_markdown_payload,
    send_email_markdown,
    send_wechat_markdown,
)


class FakeResponse:
    """模拟企业微信 webhook 响应。"""

    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        """保存响应状态和 JSON 内容。"""
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        """返回模拟 JSON。"""
        return self._payload


class FakeSMTP:
    """模拟 SMTP client。"""

    instances = []

    def __init__(self, host: str, port: int, timeout: int) -> None:
        """记录连接参数。"""
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.messages = []
        self.closed = False
        type(self).instances.append(self)

    def starttls(self) -> None:
        """记录 TLS 启用。"""
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        """记录登录参数。"""
        self.login_args = (username, password)

    def send_message(self, message) -> None:
        """记录邮件消息。"""
        self.messages.append(message)

    def quit(self) -> None:
        """记录关闭连接。"""
        self.closed = True


class TestWechatNotifications(unittest.TestCase):
    """验证企业微信消息构造与发送分支。"""

    def test_build_wechat_markdown_payload(self) -> None:
        """Markdown 报告会被包装为企业微信机器人消息格式。"""
        payload = build_wechat_markdown_payload("# 每日美股持仓简报\n\n组合净值: 100 USD")

        self.assertEqual(payload["msgtype"], "markdown")
        self.assertIn("每日美股持仓简报", payload["markdown"]["content"])
        self.assertIn("组合净值", payload["markdown"]["content"])

    def test_send_wechat_markdown_skips_when_webhook_missing(self) -> None:
        """未配置 webhook 时明确跳过，不把报告任务打失败。"""
        result = send_wechat_markdown("# report", webhook_url=None, post=lambda *args, **kwargs: None)

        self.assertFalse(result["sent"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "wechat_webhook_not_configured")

    def test_send_wechat_markdown_uses_injected_post_client(self) -> None:
        """发送时使用传入的 HTTP client，便于测试和后续替换网络层。"""
        calls = []

        def fake_post(url: str, **kwargs: object) -> FakeResponse:
            calls.append((url, kwargs))
            return FakeResponse(200, {"errcode": 0, "errmsg": "ok"})

        result = send_wechat_markdown("# report", webhook_url="https://example.test/webhook", post=fake_post)

        self.assertTrue(result["sent"])
        self.assertEqual(calls[0][0], "https://example.test/webhook")
        self.assertEqual(calls[0][1]["json"]["msgtype"], "markdown")
        self.assertEqual(calls[0][1]["timeout"], 10)


class TestEmailNotifications(unittest.TestCase):
    """验证邮件消息构造与 SMTP 发送分支。"""

    def setUp(self) -> None:
        """清理 SMTP 调用记录。"""
        FakeSMTP.instances = []

    def test_build_email_message_sets_subject_sender_and_recipients(self) -> None:
        """Markdown 报告会被包装为纯文本邮件。"""
        message = build_email_message(
            "# 每日美股持仓简报\n\n组合净值: 100 USD",
            subject="Stock-EGON 日报",
            sender="bot@example.com",
            recipients=["user@example.com"],
        )

        self.assertEqual(message["Subject"], "Stock-EGON 日报")
        self.assertEqual(message["From"], "bot@example.com")
        self.assertEqual(message["To"], "user@example.com")
        self.assertIn("每日美股持仓简报", message.get_content())

    def test_send_email_markdown_skips_when_email_missing(self) -> None:
        """未配置邮件参数时明确跳过，不把报告任务打失败。"""
        result = send_email_markdown("# report", smtp_host=None, sender=None, recipients=None, smtp_factory=FakeSMTP)

        self.assertFalse(result["sent"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "email_not_configured")
        self.assertEqual(FakeSMTP.instances, [])

    def test_send_email_markdown_uses_smtp_factory(self) -> None:
        """配置完整时通过 SMTP 登录并发送邮件。"""
        result = send_email_markdown(
            "# report",
            subject="Daily",
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="bot@example.com",
            password="secret",
            sender="bot@example.com",
            recipients="user@example.com,other@example.com",
            use_tls=True,
            smtp_factory=FakeSMTP,
        )

        self.assertTrue(result["sent"])
        smtp = FakeSMTP.instances[0]
        self.assertEqual((smtp.host, smtp.port, smtp.timeout), ("smtp.example.com", 587, 10))
        self.assertTrue(smtp.started_tls)
        self.assertEqual(smtp.login_args, ("bot@example.com", "secret"))
        self.assertEqual(smtp.messages[0]["To"], "user@example.com, other@example.com")
        self.assertTrue(smtp.closed)

    def test_send_email_markdown_supports_qq_email_shortcut_env(self) -> None:
        """QQ 邮箱只需 EMAIL_ADDRESS 和 EMAIL_AUTH_CODE 即可发送给自己。"""
        with patch.dict(
            "os.environ",
            {
                "EMAIL_ADDRESS": "user@qq.com",
                "EMAIL_AUTH_CODE": "auth-code",
            },
            clear=True,
        ):
            result = send_email_markdown("# report", subject="Daily", smtp_factory=FakeSMTP)

        self.assertTrue(result["sent"])
        smtp = FakeSMTP.instances[0]
        self.assertEqual((smtp.host, smtp.port, smtp.timeout), ("smtp.qq.com", 587, 10))
        self.assertEqual(smtp.login_args, ("user@qq.com", "auth-code"))
        self.assertEqual(smtp.messages[0]["From"], "user@qq.com")
        self.assertEqual(smtp.messages[0]["To"], "user@qq.com")


if __name__ == "__main__":
    unittest.main()
