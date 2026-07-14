"""LLM 报告增强层的单元测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from us_stock_agent.llm_enhancer import (
    enhance_report_markdown,
    enhance_report_markdown_for_email,
    load_llm_config_from_env,
)


class FakeLLMResponse:
    """模拟 OpenAI-compatible chat completion 响应。"""

    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        """保存响应状态和 JSON 内容。"""
        self.status_code = status_code
        self._payload = payload
        self.text = "response body"

    def json(self) -> dict[str, object]:
        """返回模拟 JSON。"""
        return self._payload


class TestLLMEnhancer(unittest.TestCase):
    """验证 LLM 增强层的配置解析和请求契约。"""

    def test_load_llm_config_skips_when_key_missing(self) -> None:
        """未配置 key 时明确跳过 LLM，不影响邮件发送原报告。"""
        with patch.dict("os.environ", {}, clear=True):
            config = load_llm_config_from_env()

        self.assertFalse(config.enabled)
        self.assertEqual(config.reason, "llm_not_configured")

    def test_load_llm_config_supports_deepseek_shortcut(self) -> None:
        """DeepSeek key 会推断 OpenAI-compatible base URL 和默认模型。"""
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            config = load_llm_config_from_env()

        self.assertTrue(config.enabled)
        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.base_url, "https://api.deepseek.com")
        self.assertEqual(config.model, "deepseek-chat")
        self.assertEqual(config.provider, "deepseek")

    def test_load_llm_config_supports_ark_shortcut(self) -> None:
        """火山方舟 key 会推断北京 region 的 OpenAI-compatible base URL。"""
        with patch.dict(
            "os.environ",
            {"ARK_API_KEY": "ark-secret", "ARK_MODEL": "ep-ark-model"},
            clear=True,
        ):
            config = load_llm_config_from_env()

        self.assertTrue(config.enabled)
        self.assertEqual(config.api_key, "ark-secret")
        self.assertEqual(config.base_url, "https://ark.cn-beijing.volces.com/api/v3")
        self.assertEqual(config.model, "ep-ark-model")
        self.assertEqual(config.provider, "ark")

    def test_load_llm_config_requires_ark_model(self) -> None:
        """火山方舟必须显式配置模型或接入点，避免猜错接入点。"""
        with patch.dict("os.environ", {"ARK_API_KEY": "ark-secret"}, clear=True):
            with self.assertRaisesRegex(ValueError, "ARK_MODEL"):
                load_llm_config_from_env()

    def test_load_llm_config_prefers_explicit_generic_key_over_deepseek_shortcut(self) -> None:
        """通用 LLM key 存在时不被遗留 DeepSeek key 影响默认 provider。"""
        with patch.dict(
            "os.environ",
            {
                "LLM_API_KEY": "generic-secret",
                "DEEPSEEK_API_KEY": "deepseek-secret",
                "LLM_BASE_URL": "https://api.example.com/v1",
                "LLM_MODEL": "provider/model",
            },
            clear=True,
        ):
            config = load_llm_config_from_env()

        self.assertEqual(config.api_key, "generic-secret")
        self.assertEqual(config.provider, "openai_compatible")
        self.assertEqual(config.base_url, "https://api.example.com/v1")
        self.assertEqual(config.model, "provider/model")

    def test_enhance_report_markdown_calls_openai_compatible_api(self) -> None:
        """配置完整时调用 chat completions，并返回模型改写后的 Markdown。"""
        calls = []

        def fake_post(url: str, **kwargs: object) -> FakeLLMResponse:
            calls.append((url, kwargs))
            return FakeLLMResponse(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": "# 人话版简报\n\n今天先看 NVDA 和 QQQ。"
                            }
                        }
                    ]
                },
            )

        with patch.dict(
            "os.environ",
            {
                "LLM_API_KEY": "secret",
                "LLM_BASE_URL": "https://api.example.com/v1",
                "LLM_MODEL": "provider/model",
            },
            clear=True,
        ):
            result = enhance_report_markdown(
                "# 原始报告",
                report={"module": "us_daily_report", "data": {"report_markdown": "# 原始报告"}},
                post=fake_post,
            )

        self.assertTrue(result.used)
        self.assertEqual(result.markdown, "# 人话版简报\n\n今天先看 NVDA 和 QQQ。")
        self.assertEqual(calls[0][0], "https://api.example.com/v1/chat/completions")
        self.assertEqual(calls[0][1]["headers"]["Authorization"], "Bearer secret")
        payload = calls[0][1]["json"]
        self.assertEqual(payload["model"], "provider/model")
        self.assertIn("原始报告", payload["messages"][1]["content"])
        self.assertIn("美股长期持仓复盘助理", payload["messages"][1]["content"])
        self.assertIn("1 个月、1 个季度和 1 年视角", payload["messages"][1]["content"])
        self.assertIn("每只股票使用 `### TICKER — 动作标签`", payload["messages"][1]["content"])
        self.assertIn("标题下面只写一个自然段", payload["messages"][1]["content"])
        self.assertIn("不要把规则报告改写成日内交易", payload["messages"][1]["content"])

    def test_email_enhancement_falls_back_when_llm_call_times_out(self) -> None:
        """邮件场景中 LLM 外部调用超时时应发送带警示的规则报告。"""

        def timeout_post(url: str, **kwargs: object) -> FakeLLMResponse:
            raise TimeoutError("ark request timed out")

        with patch.dict(
            "os.environ",
            {"ARK_API_KEY": "ark-secret", "ARK_MODEL": "ep-ark-model"},
            clear=True,
        ):
            result = enhance_report_markdown_for_email(
                "# 原始报告",
                report={"module": "us_daily_report", "data": {"report_markdown": "# 原始报告"}},
                post=timeout_post,
            )

        self.assertFalse(result.used)
        self.assertTrue(result.skipped)
        self.assertEqual(result.provider, "ark")
        self.assertEqual(result.model, "ep-ark-model")
        self.assertIn("llm_enhancement_failed", result.reason)
        self.assertIn("LLM 增强失败，已发送规则版报告", result.markdown)
        self.assertIn("# 原始报告", result.markdown)


if __name__ == "__main__":
    unittest.main()
