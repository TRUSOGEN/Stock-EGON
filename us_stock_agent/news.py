"""新闻源 provider 占位接口。

新闻源将在用户购买服务后接入。当前实现只定义稳定接口和环境变量约定，避免把某个供应商
提前写死。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class NewsItem:
    """新闻条目。"""

    symbol: str
    title: str
    source: str
    url: str | None = None
    risk_flag: str | None = None


class EmptyNewsProvider:
    """未配置新闻源时返回空结果。"""

    def fetch_news(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """返回空新闻结果。"""
        return {symbol: [] for symbol in symbols}


def news_provider_status() -> str:
    """返回当前新闻源配置状态。"""
    configured = [
        name
        for name in ("SERPAPI_API_KEY", "TAVILY_API_KEY", "BRAVE_API_KEY", "NEWS_API_KEY")
        if os.environ.get(name)
    ]
    if not configured:
        return "未配置新闻源，新闻和催化因素仅能由人工输入或后续 provider 补齐。"
    return f"已检测到新闻源环境变量: {', '.join(configured)}。"
