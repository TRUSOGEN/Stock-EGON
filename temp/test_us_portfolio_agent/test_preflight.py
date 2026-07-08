"""配置预检的单元测试。"""

from __future__ import annotations

import unittest

from us_stock_agent.preflight import build_preflight_report


class TestPreflight(unittest.TestCase):
    """验证配置预检会把关键缺陷显式暴露出来。"""

    def test_preflight_passes_for_valid_minimal_configuration(self) -> None:
        """最小可用配置应当通过预检。"""
        report = build_preflight_report(
            {
                "PORTFOLIO_JSON": '{"currency":"USD","cash":1000,"risk_profile":"balanced","holdings":[{"symbol":"AAPL","quantity":2,"cost_basis":180}]}',
                "EMAIL_ADDRESS": "user@qq.com",
                "EMAIL_AUTH_CODE": "auth-code",
                "BRAVE_API_KEY": "brave-key",
                "NEWS_PROVIDER_ORDER": "brave,tavily,serpapi",
            }
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["data"]["blocking_issue_count"], 0)

    def test_preflight_fails_when_ark_model_missing(self) -> None:
        """火山方舟缺少 model 时必须失败。"""
        report = build_preflight_report(
            {
                "PORTFOLIO_JSON": '{"currency":"USD","cash":1000,"risk_profile":"balanced","holdings":[{"symbol":"AAPL","quantity":2}]}',
                "EMAIL_ADDRESS": "user@qq.com",
                "EMAIL_AUTH_CODE": "auth-code",
                "ARK_API_KEY": "ark-key",
            }
        )

        self.assertFalse(report["ok"])
        self.assertIn("ARK_MODEL", "\n".join(report["errors"]))

    def test_preflight_fails_when_news_provider_order_references_unknown_provider(self) -> None:
        """未知新闻源名称必须被报出来。"""
        report = build_preflight_report(
            {
                "PORTFOLIO_JSON": '{"currency":"USD","cash":1000,"risk_profile":"balanced","holdings":[{"symbol":"AAPL","quantity":2}]}',
                "EMAIL_ADDRESS": "user@qq.com",
                "EMAIL_AUTH_CODE": "auth-code",
                "NEWS_PROVIDER_ORDER": "brave,unknown",
                "BRAVE_API_KEY": "brave-key",
            }
        )

        self.assertFalse(report["ok"])
        self.assertIn("unknown", "\n".join(report["errors"]))


if __name__ == "__main__":
    unittest.main()
