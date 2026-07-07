"""配置向导静态网页的结构测试。"""

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestConfigWizard(unittest.TestCase):
    """验证配置向导覆盖一次性配置所需字段。"""

    def test_config_wizard_exposes_required_configuration_fields(self) -> None:
        """静态网页必须能生成持仓、邮箱和新闻源配置。"""
        html = (PROJECT_ROOT / "docs" / "config-wizard.html").read_text(encoding="utf-8")

        for expected in (
            "portfolioRows",
            "serpapiKey",
            "tavilyKey",
            "braveKey",
            "emailTo",
            "emailSmtpHost",
            "emailPassword",
            "emailAddress",
            "emailAuthCode",
            "PORTFOLIO_JSON",
            "EMAIL_ADDRESS",
            "EMAIL_AUTH_CODE",
            "EMAIL_TO",
            "EMAIL_SMTP_HOST",
            "EMAIL_PASSWORD",
            "SERPAPI_API_KEY",
            "TAVILY_API_KEY",
            "BRAVE_API_KEY",
            "gh secret set",
        ):
            self.assertIn(expected, html)


if __name__ == "__main__":
    unittest.main()
