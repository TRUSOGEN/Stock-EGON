"""美股报告的可选 LLM 增强层。

本模块把已经生成的规则引擎 Markdown 报告交给 OpenAI-compatible chat
completions 接口进行二次改写。它不参与行情抓取、动作评分和风控判断，只负责把
既有结论转换成更易读的投研助理口吻。底层增强函数保持严格失败；邮件发送入口使用
显式 fallback，把 LLM 外部调用失败写入正文后继续发送规则版报告。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - 仅在极简测试环境触发
    requests = None


PostClient = Callable[..., Any]

_CONNECT_TIMEOUT_SECONDS = 10
_DEFAULT_READ_TIMEOUT_SECONDS = 30
_MAX_TIMEOUT_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 1


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
        model = model or "deepseek-chat"
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
    payload = _build_chat_completion_payload(markdown, report=report, model=active_config.model)
    response = _post_chat_completion_with_timeout_retry(
        client,
        url=_chat_completions_url(active_config.base_url),
        api_key=active_config.api_key,
        payload=payload,
        read_timeout=active_config.timeout,
    )
    status_code = getattr(response, "status_code", None)
    if status_code is None or int(status_code) < 200 or int(status_code) >= 300:
        raise ValueError(f"LLM 增强请求失败，HTTP 状态码: {status_code}。")
    enhanced_markdown = _extract_chat_completion_content(response)
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


def _post_chat_completion_with_timeout_retry(
    client: PostClient,
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    read_timeout: int,
) -> Any:
    """在短暂网络超时时有限重试 chat completions 请求。"""
    for attempt in range(_MAX_TIMEOUT_ATTEMPTS):
        try:
            return client(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(_CONNECT_TIMEOUT_SECONDS, read_timeout),
            )
        except Exception as exc:
            if not _is_retryable_timeout(exc) or attempt == _MAX_TIMEOUT_ATTEMPTS - 1:
                raise
            time.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))

    raise RuntimeError("LLM 超时重试流程未返回响应。")


def _is_retryable_timeout(exc: Exception) -> bool:
    """判断异常是否属于可安全重试的连接或读取超时。"""
    if isinstance(exc, TimeoutError):
        return True
    return bool(requests is not None and isinstance(exc, requests.exceptions.Timeout))


def _build_chat_completion_payload(markdown: str, *, report: dict[str, Any], model: str) -> dict[str, Any]:
    """构造 OpenAI-compatible chat completions 请求体。"""
    report_type = "周报" if "weekly" in str(report.get("module") or "") else "日报"
    prompt = f"""你是一个谨慎的美股长期持仓复盘助理。请把下面的规则引擎{report_type}改写成适合邮件阅读的中文 Markdown。

要求：
- 先用 3 到 5 条短句说清楚 1 个月、1 个季度和 1 年视角下最重要的结论。
- 对每只持仓说人话，解释为什么是增持候选、继续持有、重点观察或减持候选。
- 每只股票使用 `### TICKER — 动作标签` 作为小标题，标题下面只写一个自然段，不要写项目符号列表。
- 单票自然段顺序为：组合权重与盈亏状态、趋势/动量/新闻等依据、当前动作判断、进入区间/风险位/目标观察位、失效条件。
- 保留关键价格区间、风险位和失效条件，但不要堆砌表格。
- 不要把规则报告改写成日内交易、短线追涨或确定性收益建议。
- 明确说明这只是研究辅助，不构成投资建议或交易指令。
- 不要新增原报告没有支持的事实，不要编造新闻、价格或财务数据。
- 只输出最终 Markdown 正文。

原始报告：
{markdown}
"""
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
    }


def _extract_chat_completion_content(response: Any) -> str:
    """从 OpenAI-compatible 响应中提取 assistant 文本。"""
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("LLM 响应不是合法 JSON。") from exc
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM 响应缺少 choices。")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("LLM choices[0] 必须是对象。")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM choices[0].message 必须是对象。")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM 响应缺少 message.content。")
    return content.strip()


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
