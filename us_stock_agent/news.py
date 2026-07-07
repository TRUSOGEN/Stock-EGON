"""美股新闻源 provider。

本模块把外部搜索 API 统一成 `NewsItem` 列表。当前支持 Alpha Vantage、
SerpAPI、Tavily 和 Brave Search；这些 provider 都通过运行时环境变量启用，
不把任何 key 写进仓库。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import requests


@dataclass(frozen=True)
class NewsItem:
    """新闻条目。"""

    symbol: str
    title: str
    source: str
    url: str | None = None
    risk_flag: str | None = None
    snippet: str | None = None


class NewsProvider(Protocol):
    """新闻源 provider 协议。"""

    provider_name: str

    def fetch_news(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """按 ticker 拉取新闻。"""


class EmptyNewsProvider:
    """未配置新闻源时返回空结果。"""

    provider_name = "empty"

    def fetch_news(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """返回空新闻结果。"""
        return {symbol: [] for symbol in symbols}


class MultiNewsProvider:
    """按顺序聚合多个新闻源。"""

    provider_name = "multi"

    def __init__(self, providers: list[NewsProvider], *, max_items_per_symbol: int = 6) -> None:
        """保存 provider 列表和每个 ticker 的最大新闻条数。"""
        self.providers = providers
        self.max_items_per_symbol = max_items_per_symbol

    def fetch_news(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """聚合多个 provider，并按 URL 或标题去重。"""
        merged = {symbol: [] for symbol in symbols}
        seen = {symbol: set() for symbol in symbols}
        for provider in self.providers:
            provider_results = provider.fetch_news(symbols)
            for symbol in symbols:
                for item in provider_results.get(symbol, []):
                    key = item.url or item.title
                    if key in seen[symbol]:
                        continue
                    seen[symbol].add(key)
                    merged[symbol].append(item)
                    if len(merged[symbol]) >= self.max_items_per_symbol:
                        break
        return merged


class SerpAPINewsProvider:
    """SerpAPI Google Search 新闻 provider。"""

    provider_name = "serpapi"

    def __init__(self, api_key: str, *, get: Any | None = None, timeout: int = 10) -> None:
        """保存 API key 和 HTTP client。"""
        self.api_key = api_key
        self.get = get or requests.get
        self.timeout = timeout

    def fetch_news(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """通过 SerpAPI organic_results 搜索 ticker 相关新闻。"""
        results = {}
        for symbol in symbols:
            response = self.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google",
                    "q": _build_query(symbol),
                    "api_key": self.api_key,
                    "num": 5,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            items = []
            for row in _as_list(payload.get("organic_results")):
                title = _clean_text(row.get("title"))
                if not title:
                    continue
                snippet = _clean_text(row.get("snippet"))
                items.append(
                    NewsItem(
                        symbol=symbol,
                        title=title,
                        source=_clean_text(row.get("source")) or "SerpAPI",
                        url=_clean_text(row.get("link")),
                        risk_flag=_infer_risk_flag(f"{title} {snippet}"),
                        snippet=snippet,
                    )
                )
            results[symbol] = items
        return results


class TavilyNewsProvider:
    """Tavily Search 新闻 provider。"""

    provider_name = "tavily"

    def __init__(self, api_key: str, *, post: Any | None = None, timeout: int = 10) -> None:
        """保存 API key 和 HTTP client。"""
        self.api_key = api_key
        self.post = post or requests.post
        self.timeout = timeout

    def fetch_news(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """通过 Tavily search endpoint 搜索 ticker 相关新闻。"""
        results = {}
        for symbol in symbols:
            response = self.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": _build_query(symbol),
                    "search_depth": "basic",
                    "max_results": 5,
                    "include_answer": False,
                    "include_raw_content": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            items = []
            for row in _as_list(payload.get("results")):
                title = _clean_text(row.get("title"))
                if not title:
                    continue
                snippet = _clean_text(row.get("content"))
                items.append(
                    NewsItem(
                        symbol=symbol,
                        title=title,
                        source="Tavily",
                        url=_clean_text(row.get("url")),
                        risk_flag=_infer_risk_flag(f"{title} {snippet}"),
                        snippet=snippet,
                    )
                )
            results[symbol] = items
        return results


class BraveNewsProvider:
    """Brave Search 新闻 provider。"""

    provider_name = "brave"

    def __init__(self, api_key: str, *, get: Any | None = None, timeout: int = 10) -> None:
        """保存 API key 和 HTTP client。"""
        self.api_key = api_key
        self.get = get or requests.get
        self.timeout = timeout

    def fetch_news(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """通过 Brave web search 搜索 ticker 相关新闻。"""
        results = {}
        for symbol in symbols:
            response = self.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": _build_query(symbol), "count": 5, "freshness": "pw"},
                headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            items = []
            for row in _as_list(_as_mapping(payload.get("web")).get("results")):
                title = _clean_text(row.get("title"))
                if not title:
                    continue
                snippet = _clean_text(row.get("description"))
                profile = _as_mapping(row.get("profile"))
                items.append(
                    NewsItem(
                        symbol=symbol,
                        title=title,
                        source=_clean_text(profile.get("name")) or "Brave",
                        url=_clean_text(row.get("url")),
                        risk_flag=_infer_risk_flag(f"{title} {snippet}"),
                        snippet=snippet,
                    )
                )
            results[symbol] = items
        return results


class AlphaVantageNewsProvider:
    """Alpha Vantage NEWS_SENTIMENT 股票新闻 provider。"""

    provider_name = "alphavantage"

    def __init__(self, api_key: str, *, get: Any | None = None, timeout: int = 10) -> None:
        """保存 API key 和 HTTP client。"""
        self.api_key = api_key
        self.get = get or requests.get
        self.timeout = timeout

    def fetch_news(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """通过 Alpha Vantage NEWS_SENTIMENT 拉取 ticker 相关新闻。"""
        results = {}
        for symbol in symbols:
            response = self.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": symbol,
                    "sort": "LATEST",
                    "limit": 5,
                    "apikey": self.api_key,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            items = []
            for row in _as_list(payload.get("feed")):
                title = _clean_text(row.get("title"))
                if not title:
                    continue
                snippet = _clean_text(row.get("summary"))
                items.append(
                    NewsItem(
                        symbol=symbol,
                        title=title,
                        source=_clean_text(row.get("source")) or "Alpha Vantage",
                        url=_clean_text(row.get("url")),
                        risk_flag=_infer_risk_flag(f"{title} {snippet}"),
                        snippet=snippet,
                    )
                )
            results[symbol] = items
        return results


def build_news_provider_from_env(env: Mapping[str, str] | None = None) -> NewsProvider:
    """根据环境变量构建新闻 provider。"""
    source = env or os.environ
    providers_by_name: dict[str, NewsProvider] = {}
    alpha_vantage_keys = split_env_values(source.get("ALPHA_VANTAGE_API_KEY") or source.get("ALPHAVANTAGE_API_KEY"))
    serpapi_keys = split_env_values(source.get("SERPAPI_API_KEY") or source.get("SERPAPI_API_KEYS"))
    tavily_keys = split_env_values(source.get("TAVILY_API_KEY") or source.get("TAVILY_API_KEYS"))
    brave_keys = split_env_values(source.get("BRAVE_API_KEY") or source.get("BRAVE_API_KEYS"))
    if alpha_vantage_keys:
        providers_by_name["alphavantage"] = AlphaVantageNewsProvider(alpha_vantage_keys[0])
    if serpapi_keys:
        providers_by_name["serpapi"] = SerpAPINewsProvider(serpapi_keys[0])
    if tavily_keys:
        providers_by_name["tavily"] = TavilyNewsProvider(tavily_keys[0])
    if brave_keys:
        providers_by_name["brave"] = BraveNewsProvider(brave_keys[0])
    order = split_env_values(source.get("NEWS_PROVIDER_ORDER")) or ["alphavantage", "serpapi", "tavily", "brave"]
    providers = [providers_by_name[name] for name in order if name in providers_by_name]
    if not providers:
        return EmptyNewsProvider()
    max_items = _safe_int(source.get("NEWS_MAX_ITEMS_PER_SYMBOL"), default=6)
    return MultiNewsProvider(providers, max_items_per_symbol=max_items)


def news_provider_status(env: Mapping[str, str] | None = None) -> str:
    """返回当前新闻源配置状态。"""
    source = env or os.environ
    configured = [
        name
        for name in (
            "ALPHA_VANTAGE_API_KEY",
            "ALPHAVANTAGE_API_KEY",
            "SERPAPI_API_KEY",
            "SERPAPI_API_KEYS",
            "TAVILY_API_KEY",
            "TAVILY_API_KEYS",
            "BRAVE_API_KEY",
            "BRAVE_API_KEYS",
        )
        if source.get(name)
    ]
    if not configured:
        return "未配置新闻源，新闻和催化因素仅能由人工输入或后续 provider 补齐。"
    return f"已检测到新闻源环境变量: {', '.join(configured)}。"


def split_env_values(value: str | None) -> list[str]:
    """解析逗号分隔的环境变量值。"""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _build_query(symbol: str) -> str:
    """构造适合美股新闻搜索的查询词。"""
    return f"{symbol} stock earnings analyst guidance market news"


def _infer_risk_flag(text: str) -> str | None:
    """从标题和摘要中提取粗粒度风险标签。"""
    lowered = text.lower()
    if any(keyword in lowered for keyword in ("lawsuit", "probe", "investigation", "sec", "recall", "downgrade")):
        return "negative_event"
    if any(keyword in lowered for keyword in ("earnings", "guidance", "revenue", "margin")):
        return "earnings_event"
    if any(keyword in lowered for keyword in ("fed", "rate", "inflation", "tariff")):
        return "macro_event"
    return None


def _clean_text(value: object) -> str | None:
    """把外部 API 字段整理为非空字符串。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_list(value: object) -> list[dict[str, Any]]:
    """把外部 API 列表字段安全转换为对象列表。"""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_mapping(value: object) -> dict[str, Any]:
    """把外部 API 对象字段安全转换为 dict。"""
    if isinstance(value, dict):
        return value
    return {}


def _safe_int(value: object, *, default: int) -> int:
    """解析正整数配置。"""
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
