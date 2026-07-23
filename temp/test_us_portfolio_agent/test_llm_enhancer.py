"""LLM 报告增强层的单元测试。"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import requests

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

    def iter_lines(self, *, decode_unicode: bool) -> list[str]:
        """把兼容旧测试的完整 JSON 转换成一个 SSE 增量。"""
        if not decode_unicode:
            raise AssertionError("流式响应必须以文本方式读取。")
        content = self._payload["choices"][0]["message"]["content"]
        payload = {"choices": [{"delta": {"content": content}}]}
        return [f"data: {json.dumps(payload, ensure_ascii=False)}", "data: [DONE]"]


class FakeStreamingLLMResponse:
    """模拟 OpenAI-compatible SSE 流式响应。"""

    def __init__(self, status_code: int, lines: list[str]) -> None:
        """保存响应状态和逐行 SSE 内容。"""
        self.status_code = status_code
        self._lines = lines
        self.text = "response body"

    def iter_lines(self, *, decode_unicode: bool) -> list[str]:
        """返回模拟的 SSE 数据行。"""
        if not decode_unicode:
            raise AssertionError("流式响应必须以文本方式读取。")
        return self._lines


class FakeStreamingTimeoutResponse:
    """模拟 HTTP 已建立、读取 SSE 数据时才超时的响应。"""

    status_code = 200

    def iter_lines(self, *, decode_unicode: bool) -> list[str]:
        """在消费响应流时抛出 requests 读取超时。"""
        if not decode_unicode:
            raise AssertionError("流式响应必须以文本方式读取。")
        raise requests.exceptions.ReadTimeout("stream stalled")


class FakeStreamingConnectionTimeoutResponse:
    """模拟 requests 把底层 SSE 读取超时包装为 ConnectionError。"""

    status_code = 200

    def iter_lines(self, *, decode_unicode: bool) -> list[str]:
        """抛出 requests 实际流消费路径常见的超时包装异常。"""
        if not decode_unicode:
            raise AssertionError("流式响应必须以文本方式读取。")
        raise requests.exceptions.ConnectionError("HTTPSConnectionPool: Read timed out.")


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
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["max_tokens"], 1600)
        self.assertTrue(calls[0][1]["stream"])
        self.assertIn("原始报告", payload["messages"][1]["content"])
        self.assertIn("美股长期持仓复盘助理", payload["messages"][1]["content"])
        self.assertIn("1 个月、1 个季度和 1 年视角", payload["messages"][1]["content"])
        self.assertIn("每只股票使用 `### TICKER — 动作标签`", payload["messages"][1]["content"])
        self.assertIn("标题下面只写一个自然段", payload["messages"][1]["content"])
        self.assertIn("不要把规则报告改写成日内交易", payload["messages"][1]["content"])

    def test_enhance_report_markdown_assembles_sse_delta_content(self) -> None:
        """流式响应应按顺序拼接每个 SSE delta 的 Markdown 内容。"""
        def fake_post(url: str, **kwargs: object) -> FakeStreamingLLMResponse:
            return FakeStreamingLLMResponse(
                200,
                [
                    'data: {"choices":[{"delta":{"content":"# 人话版"}}]}',
                    "",
                    'data: {"choices":[{"delta":{"content":"简报\\n\\n继续持有。"}}]}',
                    "data: [DONE]",
                ],
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
                report={"module": "us_daily_report"},
                post=fake_post,
            )

        self.assertTrue(result.used)
        self.assertEqual(result.markdown, "# 人话版简报\n\n继续持有。")

    def test_enhance_report_markdown_retries_once_after_read_timeout(self) -> None:
        """首次读取超时后应等待一次并使用第二次成功响应。"""
        calls = []

        def flaky_post(url: str, **kwargs: object) -> FakeLLMResponse:
            calls.append((url, kwargs))
            if len(calls) == 1:
                raise TimeoutError("temporary ark timeout")
            return FakeLLMResponse(
                200,
                {"choices": [{"message": {"content": "# 增强后的报告"}}]},
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
            with patch("time.sleep") as sleep:
                result = enhance_report_markdown_for_email(
                    "# 原始报告",
                    report={"module": "us_daily_report"},
                    post=flaky_post,
                )

        self.assertTrue(result.used)
        self.assertEqual(result.markdown, "# 增强后的报告")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1]["timeout"], (10, 30))
        sleep.assert_called_once_with(1)

    def test_enhance_report_markdown_retries_when_sse_consumption_times_out(self) -> None:
        """HTTP 已建立但 SSE 读取超时时也应重新发起一次完整请求。"""
        calls = []

        def flaky_stream_post(url: str, **kwargs: object):
            calls.append((url, kwargs))
            if len(calls) == 1:
                return FakeStreamingTimeoutResponse()
            return FakeStreamingLLMResponse(
                200,
                [
                    'data: {"choices":[{"delta":{"content":"# 重试成功"}}]}',
                    "data: [DONE]",
                ],
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
            with patch("time.sleep") as sleep:
                result = enhance_report_markdown_for_email(
                    "# 原始报告",
                    report={"module": "us_daily_report"},
                    post=flaky_stream_post,
                )

        self.assertTrue(result.used)
        self.assertEqual(result.markdown, "# 重试成功")
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once_with(1)

    def test_enhance_report_markdown_retries_wrapped_sse_read_timeout(self) -> None:
        """requests 包装后的 SSE ReadTimeout 仍应重试完整请求。"""
        calls = []

        def flaky_stream_post(url: str, **kwargs: object):
            calls.append((url, kwargs))
            if len(calls) == 1:
                return FakeStreamingConnectionTimeoutResponse()
            return FakeStreamingLLMResponse(
                200,
                [
                    'data: {"choices":[{"delta":{"content":"# 包装超时重试成功"}}]}',
                    "data: [DONE]",
                ],
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
            with patch("time.sleep") as sleep:
                result = enhance_report_markdown_for_email(
                    "# 原始报告",
                    report={"module": "us_daily_report"},
                    post=flaky_stream_post,
                )

        self.assertTrue(result.used)
        self.assertEqual(result.markdown, "# 包装超时重试成功")
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once_with(1)

    def test_email_enhancement_falls_back_when_llm_call_times_out(self) -> None:
        """邮件场景中 LLM 外部调用超时时应发送带警示的规则报告。"""

        def timeout_post(url: str, **kwargs: object) -> FakeLLMResponse:
            raise TimeoutError("ark request timed out")

        with patch.dict(
            "os.environ",
            {"ARK_API_KEY": "ark-secret", "ARK_MODEL": "ep-ark-model"},
            clear=True,
        ):
            with patch("time.sleep"):
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

    def test_email_enhancement_falls_back_after_retry_attempts_are_exhausted(self) -> None:
        """两次读取超时后应保留最终错误并发送规则报告。"""
        calls = []

        def timeout_post(url: str, **kwargs: object) -> FakeLLMResponse:
            calls.append((url, kwargs))
            raise TimeoutError("persistent ark timeout")

        with patch.dict(
            "os.environ",
            {"ARK_API_KEY": "ark-secret", "ARK_MODEL": "ep-ark-model"},
            clear=True,
        ):
            with patch("time.sleep") as sleep:
                result = enhance_report_markdown_for_email(
                    "# 原始报告",
                    report={"module": "us_daily_report"},
                    post=timeout_post,
                )

        self.assertFalse(result.used)
        self.assertTrue(result.skipped)
        self.assertEqual(len(calls), 2)
        self.assertIn("persistent ark timeout", result.reason)
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
