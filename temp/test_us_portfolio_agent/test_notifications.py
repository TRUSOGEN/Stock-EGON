"""微信通知层的单元测试。"""

from __future__ import annotations

import unittest

from us_stock_agent.notifications import build_wechat_markdown_payload, send_wechat_markdown


class FakeResponse:
    """模拟企业微信 webhook 响应。"""

    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        """保存响应状态和 JSON 内容。"""
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        """返回模拟 JSON。"""
        return self._payload


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


if __name__ == "__main__":
    unittest.main()
