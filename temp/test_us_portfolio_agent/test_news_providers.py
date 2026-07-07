"""美股新闻源 provider 的单元测试。"""

from __future__ import annotations

import unittest

from us_stock_agent.news import (
    BraveNewsProvider,
    SerpAPINewsProvider,
    TavilyNewsProvider,
    build_news_provider_from_env,
    split_env_values,
)


class FakeResponse:
    """模拟 HTTP JSON 响应。"""

    def __init__(self, payload: dict[str, object]) -> None:
        """保存响应 JSON。"""
        self._payload = payload

    def raise_for_status(self) -> None:
        """模拟成功 HTTP 响应。"""

    def json(self) -> dict[str, object]:
        """返回响应 JSON。"""
        return self._payload


class TestNewsProviders(unittest.TestCase):
    """验证新闻搜索 provider 的解析和环境变量选择。"""

    def test_split_env_values_supports_single_and_multiple_keys(self) -> None:
        """环境变量解析支持逗号分隔并丢弃空值。"""
        self.assertEqual(split_env_values(" a, ,b ,, c "), ["a", "b", "c"])

    def test_serpapi_provider_parses_organic_results(self) -> None:
        """SerpAPI organic_results 会解析为 NewsItem。"""
        calls = []

        def fake_get(url: str, **kwargs: object) -> FakeResponse:
            calls.append((url, kwargs))
            return FakeResponse(
                {
                    "organic_results": [
                        {
                            "title": "Nvidia announces new AI chip",
                            "link": "https://example.com/nvda",
                            "source": "Example News",
                            "snippet": "Nvidia demand remains strong.",
                        }
                    ]
                }
            )

        provider = SerpAPINewsProvider(api_key="key", get=fake_get)
        result = provider.fetch_news(["NVDA"])

        self.assertEqual(result["NVDA"][0].title, "Nvidia announces new AI chip")
        self.assertEqual(result["NVDA"][0].source, "Example News")
        self.assertEqual(result["NVDA"][0].url, "https://example.com/nvda")
        self.assertIn("q", calls[0][1]["params"])

    def test_tavily_provider_parses_results(self) -> None:
        """Tavily results 会解析为 NewsItem。"""
        def fake_post(url: str, **kwargs: object) -> FakeResponse:
            return FakeResponse(
                {
                    "results": [
                        {
                            "title": "Tesla earnings preview",
                            "url": "https://example.com/tsla",
                            "content": "Margins and deliveries are in focus.",
                        }
                    ]
                }
            )

        provider = TavilyNewsProvider(api_key="key", post=fake_post)
        result = provider.fetch_news(["TSLA"])

        self.assertEqual(result["TSLA"][0].title, "Tesla earnings preview")
        self.assertEqual(result["TSLA"][0].source, "Tavily")

    def test_brave_provider_parses_web_results(self) -> None:
        """Brave web results 会解析为 NewsItem。"""
        def fake_get(url: str, **kwargs: object) -> FakeResponse:
            return FakeResponse(
                {
                    "web": {
                        "results": [
                            {
                                "title": "Market awaits Fed decision",
                                "url": "https://example.com/fed",
                                "description": "Rates remain the macro focus.",
                                "profile": {"name": "Macro Wire"},
                            }
                        ]
                    }
                }
            )

        provider = BraveNewsProvider(api_key="key", get=fake_get)
        result = provider.fetch_news(["SPY"])

        self.assertEqual(result["SPY"][0].title, "Market awaits Fed decision")
        self.assertEqual(result["SPY"][0].source, "Macro Wire")

    def test_build_news_provider_from_env_uses_configured_order(self) -> None:
        """环境变量会构建多 provider 聚合器。"""
        provider = build_news_provider_from_env(
            {
                "SERPAPI_API_KEY": "serp",
                "TAVILY_API_KEYS": "tav1,tav2",
                "NEWS_PROVIDER_ORDER": "tavily,serpapi",
            }
        )

        self.assertEqual([item.provider_name for item in provider.providers], ["tavily", "serpapi"])


if __name__ == "__main__":
    unittest.main()
