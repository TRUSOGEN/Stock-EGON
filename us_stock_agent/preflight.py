"""运行前配置预检。

本模块只做静态和轻量级检查，不访问外部 API，不打印敏感值。它的职责是尽早暴露
持仓 JSON、邮件配置、LLM 配置、新闻源顺序和图表开关中的结构性问题，让用户在
点 GitHub Actions 之前就知道哪里会失败。
"""

from __future__ import annotations

import importlib.util
from typing import Any, Mapping

from a_stock_quant.output import make_result

from .news import DEFAULT_NEWS_PROVIDER_ORDER, SUPPORTED_NEWS_PROVIDERS, split_env_values
from .notifications import _is_qq_email, _parse_bool
from .portfolio import load_portfolio_from_json


def build_preflight_report(env: Mapping[str, str]) -> dict[str, Any]:
    """构建结构化预检报告。"""
    checks: list[dict[str, str]] = []
    warnings: list[str] = []
    errors: list[str] = []

    _check_portfolio(env, checks, errors)
    _check_email(env, checks, errors)
    _check_llm(env, checks, errors, warnings)
    _check_news(env, checks, errors, warnings)
    _check_charting(env, checks, errors, warnings)

    result = make_result(
        module="preflight",
        data={
            "checks": checks,
            "blocking_issue_count": len(errors),
            "warning_count": len(warnings),
            "default_news_provider_order": list(DEFAULT_NEWS_PROVIDER_ORDER),
        },
        data_time=None,
        source_api="local_env",
        warnings=warnings or ["预检只检查配置结构，不会验证外部 API key 是否真实可用。"],
    )
    if errors:
        result["ok"] = False
        result["errors"] = errors
    return result


def _check_portfolio(env: Mapping[str, str], checks: list[dict[str, str]], errors: list[str]) -> None:
    """检查持仓 JSON 是否存在且可解析。"""
    value = env.get("PORTFOLIO_JSON", "").strip()
    if not value:
        errors.append("缺少 PORTFOLIO_JSON。")
        checks.append({"name": "portfolio", "status": "error", "detail": "未检测到 PORTFOLIO_JSON。"})
        return
    try:
        portfolio = load_portfolio_from_json(value)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"PORTFOLIO_JSON 无法解析: {exc}")
        checks.append({"name": "portfolio", "status": "error", "detail": "PORTFOLIO_JSON 结构无效。"})
        return
    checks.append(
        {
            "name": "portfolio",
            "status": "ok",
            "detail": f"已检测到 {len(portfolio.holdings)} 条持仓，币种 {portfolio.currency}。",
        }
    )


def _check_email(env: Mapping[str, str], checks: list[dict[str, str]], errors: list[str]) -> None:
    """检查 QQ 快捷邮箱或完整 SMTP 配置。"""
    email_address = env.get("EMAIL_ADDRESS", "").strip()
    auth_code = env.get("EMAIL_AUTH_CODE", "").strip()
    if email_address or auth_code:
        if not email_address or not auth_code:
            errors.append("QQ 邮箱快捷配置不完整：需要同时提供 EMAIL_ADDRESS 和 EMAIL_AUTH_CODE。")
            checks.append({"name": "email", "status": "error", "detail": "QQ 邮箱快捷配置缺字段。"})
            return
        if not _is_qq_email(email_address):
            errors.append("EMAIL_ADDRESS 当前不是 QQ 邮箱，不能走 QQ 快捷配置。")
            checks.append({"name": "email", "status": "error", "detail": "快捷邮箱地址不是 @qq.com。"})
            return
        checks.append({"name": "email", "status": "ok", "detail": "QQ 邮箱快捷发送配置完整。"})
        return

    smtp_host = env.get("EMAIL_SMTP_HOST", "").strip()
    if not smtp_host:
        errors.append("未检测到邮件发送配置。请配置 QQ 邮箱快捷字段或完整 SMTP 字段。")
        checks.append({"name": "email", "status": "error", "detail": "缺少邮件发送配置。"})
        return
    required = {
        "EMAIL_USERNAME": env.get("EMAIL_USERNAME", "").strip(),
        "EMAIL_PASSWORD": env.get("EMAIL_PASSWORD", "").strip(),
        "EMAIL_FROM": env.get("EMAIL_FROM", "").strip(),
        "EMAIL_TO": env.get("EMAIL_TO", "").strip(),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        errors.append(f"SMTP 配置不完整，缺少: {', '.join(missing)}。")
        checks.append({"name": "email", "status": "error", "detail": "完整 SMTP 配置缺字段。"})
        return
    checks.append({"name": "email", "status": "ok", "detail": "完整 SMTP 配置看起来齐全。"})


def _check_llm(
    env: Mapping[str, str],
    checks: list[dict[str, str]],
    errors: list[str],
    warnings: list[str],
) -> None:
    """检查 LLM 增强层的关键组合。"""
    ark_key = env.get("ARK_API_KEY", "").strip() or env.get("VOLCENGINE_ARK_API_KEY", "").strip()
    deepseek_key = env.get("DEEPSEEK_API_KEY", "").strip()
    llm_key = env.get("LLM_API_KEY", "").strip()
    openai_key = env.get("OPENAI_API_KEY", "").strip()
    if not any((ark_key, deepseek_key, llm_key, openai_key)):
        checks.append({"name": "llm", "status": "skipped", "detail": "未启用 LLM 增强，将直接发送规则报告。"})
        return
    if ark_key:
        ark_model = env.get("ARK_MODEL", "").strip() or env.get("LLM_MODEL", "").strip() or env.get("OPENAI_MODEL", "").strip()
        if not ark_model:
            errors.append("火山方舟配置不完整：缺少 ARK_MODEL。")
            checks.append({"name": "llm", "status": "error", "detail": "ARK_API_KEY 已配置，但 ARK_MODEL 缺失。"})
            return
        checks.append({"name": "llm", "status": "ok", "detail": "火山方舟配置完整。"})
        return
    if deepseek_key:
        checks.append({"name": "llm", "status": "ok", "detail": "DeepSeek 官方接口配置已启用。"})
        return
    if llm_key:
        if not env.get("LLM_BASE_URL", "").strip() or not env.get("LLM_MODEL", "").strip():
            errors.append("通用 LLM 配置不完整：LLM_API_KEY 需要同时配 LLM_BASE_URL 和 LLM_MODEL。")
            checks.append({"name": "llm", "status": "error", "detail": "通用 OpenAI-compatible 配置缺字段。"})
            return
        checks.append({"name": "llm", "status": "ok", "detail": "通用 OpenAI-compatible 配置完整。"})
        return
    if openai_key:
        checks.append({"name": "llm", "status": "ok", "detail": "OPENAI_API_KEY 已启用，将使用默认 OpenAI 配置。"})
        warnings.append("如果 OPENAI_API_KEY 实际不是 OpenAI 官方 key，请同步填写 OPENAI_BASE_URL 和 OPENAI_MODEL。")


def _check_news(
    env: Mapping[str, str],
    checks: list[dict[str, str]],
    errors: list[str],
    warnings: list[str],
) -> None:
    """检查新闻源 key 和 provider 顺序。"""
    mapping = {
        "brave": env.get("BRAVE_API_KEY", "").strip() or env.get("BRAVE_API_KEYS", "").strip(),
        "tavily": env.get("TAVILY_API_KEY", "").strip() or env.get("TAVILY_API_KEYS", "").strip(),
        "serpapi": env.get("SERPAPI_API_KEY", "").strip() or env.get("SERPAPI_API_KEYS", "").strip(),
        "alphavantage": env.get("ALPHA_VANTAGE_API_KEY", "").strip() or env.get("ALPHAVANTAGE_API_KEY", "").strip(),
    }
    configured = [name for name, value in mapping.items() if value]
    order = split_env_values(env.get("NEWS_PROVIDER_ORDER")) or list(DEFAULT_NEWS_PROVIDER_ORDER)
    unknown = [name for name in order if name not in SUPPORTED_NEWS_PROVIDERS]
    if unknown:
        errors.append(f"NEWS_PROVIDER_ORDER 含未知 provider: {', '.join(unknown)}。")
        checks.append({"name": "news", "status": "error", "detail": "新闻源顺序里含未支持的名称。"})
        return
    if not configured:
        warnings.append("未配置新闻源，报告将没有自动抓取的事件催化信息。")
        checks.append({"name": "news", "status": "skipped", "detail": "未检测到新闻源 key。"})
        return
    missing_for_order = [name for name in order if name not in configured]
    if missing_for_order:
        warnings.append(f"NEWS_PROVIDER_ORDER 中这些 provider 当前没有 key，会被自动跳过: {', '.join(missing_for_order)}。")
    checks.append({"name": "news", "status": "ok", "detail": f"已配置新闻源: {', '.join(configured)}。"})


def _check_charting(
    env: Mapping[str, str],
    checks: list[dict[str, str]],
    errors: list[str],
    warnings: list[str],
) -> None:
    """检查邮件图表开关和本地依赖。"""
    enabled = _parse_bool(env.get("EMAIL_INCLUDE_CHARTS"), default=False)
    if not enabled:
        checks.append({"name": "charts", "status": "skipped", "detail": "未启用邮件 K 线附件。"})
        return
    missing = [name for name in ("pandas", "PIL", "yfinance") if importlib.util.find_spec(name) is None]
    if missing:
        errors.append(f"邮件 K 线附件依赖缺失: {', '.join(missing)}。")
        checks.append({"name": "charts", "status": "error", "detail": "K 线附件已启用，但本地依赖不完整。"})
        return
    checks.append({"name": "charts", "status": "ok", "detail": "邮件将附带每只股票的周/月/年三联 K 线图。"})
    warnings.append("K 线附件会增加邮件体积；持仓很多时应关注收件箱大小限制。")
