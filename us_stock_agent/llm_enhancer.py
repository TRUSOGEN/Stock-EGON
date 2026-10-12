"""美股报告的可选 LLM 增强层。

本模块优先基于结构化证据生成可校验的分析，保留程序报告原文。旧 JSON 缺少证据包
时兼容既有改写路径；外部服务失败时显式降级，不阻断核心邮件。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Callable

from .evidence_analysis import build_analysis_payload, validate_and_render_analysis

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - 仅在极简测试环境触发
    requests = None


PostClient = Callable[..., Any]

_CONNECT_TIMEOUT_SECONDS = 10
_DEFAULT_READ_TIMEOUT_SECONDS = 30
_DEFAULT_MAX_TOKENS = 16384
_MAX_TIMEOUT_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 1
_REPORT_REWRITE_PROMPT_PATH = Path(__file__).with_name("prompts") / "report_rewrite.md"


@dataclass(frozen=True)
class LLMConfig:
    """LLM 增强层运行配置。"""

    enabled: bool
    api_key: str | None
    base_url: str | None
    model: str | None
    provider: str | None
    reason: str | None = None
    timeout: int = 45
    max_tokens: int = _DEFAULT_MAX_TOKENS


@dataclass(frozen=True)
class LLMEnhanceResult:
    """LLM 增强结果和可审计元数据。"""

    markdown: str
    used: bool
    skipped: bool
    reason: str | None
    model: str | None = None
    provider: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        """转换为邮件发送结果中的机器可读元数据。"""
        return {
            "used": self.used,
            "skipped": self.skipped,
            "reason": self.reason,
            "model": self.model,
            "provider": self.provider,
        }


def load_llm_config_from_env() -> LLMConfig:
    """从环境变量读取 OpenAI-compatible LLM 配置。"""
    llm_key = _read_env("LLM_API_KEY")
    openai_key = _read_env("OPENAI_API_KEY")
    ark_key = _read_env("ARK_API_KEY") or _read_env("VOLCENGINE_ARK_API_KEY")
    deepseek_key = _read_env("DEEPSEEK_API_KEY")
    api_key = llm_key or openai_key or ark_key or deepseek_key
    if not api_key:
        return LLMConfig(
            enabled=False,
            api_key=None,
            base_url=None,
            model=None,
            provider=None,
            reason="llm_not_configured",
        )

    provider = _infer_provider(api_key_source=_api_key_source(llm_key=llm_key, openai_key=openai_key, ark_key=ark_key))
    base_url = _read_env("LLM_BASE_URL") or _read_env("OPENAI_BASE_URL") or _read_env("ARK_BASE_URL")
    model = _read_env("LLM_MODEL") or _read_env("OPENAI_MODEL") or _read_env("ARK_MODEL") or _read_env("DEEPSEEK_MODEL")
    if provider == "deepseek":
        base_url = base_url or "https://api.deepseek.com"
        model = model or "deepseek-flash"
    elif provider == "ark":
        base_url = base_url or "https://ark.cn-beijing.volces.com/api/v3"
        if not model:
            raise ValueError("火山方舟配置不完整：需要 ARK_MODEL、LLM_MODEL 或 OPENAI_MODEL。")
    else:
        base_url = base_url or "https://api.openai.com/v1"
        model = model or "gpt-4o-mini"

    return LLMConfig(
        enabled=True,
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider=provider,
        timeout=_parse_int(_read_env("LLM_TIMEOUT_SECONDS"), default=_DEFAULT_READ_TIMEOUT_SECONDS),
        max_tokens=_parse_positive_int(_read_env("LLM_MAX_TOKENS"), default=_DEFAULT_MAX_TOKENS),
    )


def enhance_report_markdown(
    markdown: str,
    *,
    report: dict[str, Any],
    config: LLMConfig | None = None,
    post: PostClient | None = None,
) -> LLMEnhanceResult:
    """按需调用 LLM，把规则报告改写为更易读的邮件正文。"""
    active_config = config or load_llm_config_from_env()
    if not active_config.enabled:
        return LLMEnhanceResult(
            markdown=markdown,
            used=False,
            skipped=True,
            reason=active_config.reason,
        )
    if not active_config.api_key or not active_config.base_url or not active_config.model:
        raise ValueError("LLM 配置不完整：需要 api_key、base_url 和 model。")

    if post is not None:
        client = post
    elif requests is not None:
        client = requests.post
    else:
        raise RuntimeError("当前环境缺少 requests，无法调用 LLM 增强接口。")
    evidence = report.get("data", {}).get("evidence")
    payload = build_analysis_payload(evidence, model=active_config.model, max_tokens=active_config.max_tokens) if evidence else _build_chat_completion_payload(
        markdown,
        report=report,
        model=active_config.model,
        max_tokens=active_config.max_tokens,
    )
    if _is_deepseek_api(active_config.base_url):
        payload["thinking"] = {"type": "enabled" if evidence else "disabled"}
        if evidence:
            payload["reasoning_effort"] = "high"
    enhanced_markdown = _request_streaming_chat_completion_with_timeout_retry(
        client,
        url=_chat_completions_url(active_config.base_url),
        api_key=active_config.api_key,
        payload=payload,
        read_timeout=active_config.timeout,
    )
    if evidence:
        analysis = validate_and_render_analysis(enhanced_markdown, evidence)
        enhanced_markdown = markdown.rstrip() + "\n\n" + analysis
    return LLMEnhanceResult(
        markdown=enhanced_markdown,
        used=True,
        skipped=False,
        reason=None,
        model=active_config.model,
        provider=active_config.provider,
    )


def enhance_report_markdown_for_email(
    markdown: str,
    *,
    report: dict[str, Any],
    config: LLMConfig | None = None,
    post: PostClient | None = None,
) -> LLMEnhanceResult:
    """邮件发送场景的 LLM 增强入口。

    邮件报告的核心价值是把已经生成的规则版日报送达。LLM 改写属于可选增强：未配置
    时正常跳过；配置完整但外部 API 超时、限流或返回异常时，在正文顶部加入明确警示，
    然后发送规则版报告。配置读取本身的结构性错误仍会抛出，让错误正确暴露。
    """
    active_config = config or load_llm_config_from_env()
    if not active_config.enabled:
        return enhance_report_markdown(markdown, report=report, config=active_config, post=post)
    try:
        return enhance_report_markdown(markdown, report=report, config=active_config, post=post)
    except Exception as exc:  # noqa: BLE001
        reason = f"llm_enhancement_failed: {exc}"
        return LLMEnhanceResult(
            markdown=_prepend_llm_failure_notice(markdown, error=str(exc)),
            used=False,
            skipped=True,
            reason=reason,
            model=active_config.model,
            provider=active_config.provider,
        )


def _prepend_llm_failure_notice(markdown: str, *, error: str) -> str:
    """在规则报告顶部加入 LLM 增强失败提示。"""
    return (
        "> LLM 增强失败，已发送规则版报告。"
        f"失败原因: {error}\n\n"
        f"{markdown.strip()}"
    )


def _request_streaming_chat_completion_with_timeout_retry(
    client: PostClient,
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    read_timeout: int,
) -> str:
    """在短暂网络超时时重试完整的流式 chat completions 请求。"""
    for attempt in range(_MAX_TIMEOUT_ATTEMPTS):
        try:
            response = client(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(_CONNECT_TIMEOUT_SECONDS, read_timeout),
                stream=True,
            )
            status_code = getattr(response, "status_code", None)
            if status_code is None or int(status_code) < 200 or int(status_code) >= 300:
                raise ValueError(f"LLM 增强请求失败，HTTP 状态码: {status_code}。")
            try:
                return _extract_streaming_chat_completion_content(response)
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except Exception as exc:
            if not _is_retryable_timeout(exc) or attempt == _MAX_TIMEOUT_ATTEMPTS - 1:
                raise
            time.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))

    raise RuntimeError("LLM 超时重试流程未返回响应。")


def _is_retryable_timeout(exc: Exception) -> bool:
    """判断异常是否属于可安全重试的连接或读取超时。"""
    if isinstance(exc, TimeoutError):
        return True
    if requests is None:
        return False
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if not isinstance(exc, requests.exceptions.ConnectionError):
        return False

    pending: list[BaseException] = [exc]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, (TimeoutError, requests.exceptions.Timeout)):
            return True
        if type(current).__name__ == "ReadTimeoutError":
            return True
        pending.extend(item for item in current.args if isinstance(item, BaseException))
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)

    return "read timed out" in str(exc).lower()


def _build_chat_completion_payload(
    markdown: str,
    *,
    report: dict[str, Any],
    model: str,
    max_tokens: int,
) -> dict[str, Any]:
    """构造 OpenAI-compatible chat completions 请求体。"""
    report_type = "周报" if "weekly" in str(report.get("module") or "") else "日报"
    prompt = _REPORT_REWRITE_PROMPT_PATH.read_text(encoding="utf-8").format(
        report_type=report_type,
        report_instructions=_report_rewrite_instructions(report_type),
        markdown=markdown,
    )
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你只基于用户提供的报告改写，不编造事实，并保持风险提示清楚。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": True,
    }


def _report_rewrite_instructions(report_type: str) -> str:
    """返回与报告周期匹配的决策优先级写作要求。"""
    if report_type == "日报":
        return """日报输出顺序：
- 先以 `## 今日优先复核` 列出最多三项优先复核事项，按风险与组合权重排序。
- 只展开减持候选、增持候选、触及风险位或高权重重点观察；每项使用 `### TICKER — 动作标签`。
- 普通继续持有和低权重重点观察压缩为一行，放入 `## 其余持仓`。
- 价格区间必须说明其用途，例如风险位、重新评估区间或观察目标；只保留与当前动作有关的数字。"""
    return """周报输出顺序：
- 先按 1 个月、1 个季度和 1 年三个周期总结组合变化，并给出最多三项下周复核重点。
- 只展开动作变化、风险上升或组合权重前 3 的标的；其余标的放入简短观察清单。
- 价格区间必须说明其用途，并优先保留影响下周复核的风险位与失效条件。"""


def _is_deepseek_api(base_url: str) -> bool:
    """判断当前请求是否发往 DeepSeek 官方 OpenAI-compatible API。"""
    return base_url.rstrip("/").lower() in {"https://api.deepseek.com", "https://api.deepseek.com/v1"}


def _extract_streaming_chat_completion_content(response: Any) -> str:
    """从 OpenAI-compatible SSE 响应顺序拼接 assistant 文本。"""
    iter_lines = getattr(response, "iter_lines", None)
    if not callable(iter_lines):
        raise ValueError("LLM 流式响应缺少 iter_lines。")

    fragments: list[str] = []
    completed = False
    for event_index, data in enumerate(_iter_sse_data_events(iter_lines(decode_unicode=True)), start=1):
        if data == "[DONE]":
            completed = True
            break
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM 流式响应第 {event_index} 个 data 事件包含非法 JSON（第 {exc.lineno} 行第 {exc.colno} 列）。"
            ) from exc
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ValueError("LLM 流式响应缺少 choices。")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ValueError("LLM 流式响应 choices[0] 必须是对象。")
        delta = first_choice.get("delta")
        if not isinstance(delta, dict):
            raise ValueError("LLM 流式响应 choices[0].delta 必须是对象。")
        if first_choice.get("finish_reason") in {"length", "content_filter"}:
            raise ValueError("LLM 输出被截断或过滤，不能作为完整分析发送。")
        content = delta.get("content")
        if content is None:
            continue
        if not isinstance(content, str):
            raise ValueError("LLM 流式响应 delta.content 必须是字符串。")
        fragments.append(content)

    if not completed:
        raise ValueError("LLM 流式响应未以 [DONE] 结束。")
    markdown = "".join(fragments).strip()
    if not markdown:
        raise ValueError("LLM 流式响应缺少 delta.content。")
    return markdown


def _iter_sse_data_events(lines: Iterable[str]) -> Iterator[str]:
    """按 SSE 事件边界合并 data 行，并兼容首行 UTF-8 BOM。"""
    pending_data_lines: list[str] = []
    for raw_line in lines:
        if not isinstance(raw_line, str):
            raise ValueError("LLM 流式响应包含非文本数据行。")
        line = raw_line.lstrip("\ufeff")
        if not line:
            if pending_data_lines:
                yield "\n".join(pending_data_lines)
                pending_data_lines.clear()
            continue
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            if pending_data_lines:
                yield "\n".join(pending_data_lines)
                pending_data_lines.clear()
            yield data
            continue
        pending_data_lines.append(data)
    if pending_data_lines:
        yield "\n".join(pending_data_lines)


def _chat_completions_url(base_url: str) -> str:
    """拼出 chat completions endpoint。"""
    return f"{base_url.rstrip('/')}/chat/completions"


def _api_key_source(*, llm_key: str | None, openai_key: str | None, ark_key: str | None) -> str:
    """根据 key 优先级返回实际使用的 key 来源。"""
    if llm_key:
        return "llm"
    if openai_key:
        return "openai"
    if ark_key:
        return "ark"
    return "deepseek"


def _infer_provider(*, api_key_source: str) -> str:
    """根据配置来源推断 provider 名称。"""
    explicit_provider = _read_env("LLM_PROVIDER")
    if explicit_provider:
        return explicit_provider
    if api_key_source == "ark":
        return "ark"
    if api_key_source == "deepseek":
        return "deepseek"
    return "openai_compatible"


def _read_env(name: str) -> str | None:
    """读取非空环境变量。"""
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_int(value: str | None, *, default: int) -> int:
    """解析整数环境变量。"""
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_positive_int(value: str | None, *, default: int) -> int:
    """解析必须为正整数的输出 token 上限。"""
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError("LLM_MAX_TOKENS 必须是正整数。") from exc
    if parsed <= 0:
        raise ValueError("LLM_MAX_TOKENS 必须是正整数。")
    return parsed
