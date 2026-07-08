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
            "alphaVantageKey",
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
            "llmApiKey",
            "llmBaseUrl",
            "llmModel",
            "arkApiKey",
            "arkModel",
            "deepseekApiKey",
            "ARK_API_KEY",
            "ARK_MODEL",
            "LLM_API_KEY",
            "LLM_BASE_URL",
            "LLM_MODEL",
            "DEEPSEEK_API_KEY",
            "ALPHA_VANTAGE_API_KEY",
            "SERPAPI_API_KEY",
            "TAVILY_API_KEY",
            "BRAVE_API_KEY",
            "oneShotSecretScript",
            "直接复制下面这一段到终端",
            "EMAIL_INCLUDE_CHARTS",
            "brave,tavily,serpapi,alphavantage",
            "gh secret set --repo ${repo} -f -",
        ):
            self.assertIn(expected, html)

    def test_docs_link_to_hosted_config_wizard_page(self) -> None:
        """README 和部署文档应当给出可直接打开的网页入口。"""
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        deployment = (PROJECT_ROOT / "docs" / "us-stock-agent-deployment.md").read_text(encoding="utf-8")
        beginner = (PROJECT_ROOT / "docs" / "github-actions-beginner.md").read_text(encoding="utf-8")

        expected = "https://trusogen.github.io/Stock-EGON/config-wizard.html"
        self.assertIn(expected, readme)
        self.assertIn(expected, deployment)
        self.assertIn(expected, beginner)

    def test_repo_contains_github_pages_workflow_for_docs(self) -> None:
        """仓库应包含把 docs 发布为网页的 GitHub Pages workflow。"""
        workflow = PROJECT_ROOT / ".github" / "workflows" / "deploy-docs-pages.yml"
        self.assertTrue(workflow.exists())
        content = workflow.read_text(encoding="utf-8")
        self.assertIn("actions/deploy-pages@v4", content)
        self.assertIn("actions/upload-pages-artifact@v3", content)

    def test_docs_include_interactive_stock_chart_page(self) -> None:
        """docs 应提供可由邮件链接打开的交互图页面。"""
        html = (PROJECT_ROOT / "docs" / "stock-chart.html").read_text(encoding="utf-8")

        self.assertIn("symbol", html)
        self.assertIn("Stock-EGON 交互图", html)
        self.assertIn("TradingView", html)
        self.assertIn("finance.yahoo.com", html)
        self.assertNotIn("data/us-stock-charts.json", html)

    def test_methodology_doc_records_daily_stock_analysis_and_strategy_skill_sources(self) -> None:
        """方法论文档应记录参考来源和本项目的取舍边界。"""
        markdown = (PROJECT_ROOT / "docs" / "methodology.md").read_text(encoding="utf-8")

        for expected in (
            "ZhuLinsen/daily_stock_analysis",
            "bull_trend",
            "volume_breakout",
            "event_driven",
            "growth_quality",
            "不是交易指令",
            "未回测验证前",
        ):
            self.assertIn(expected, markdown)

    def test_config_wizard_persists_last_form_values_locally(self) -> None:
        """配置向导应在浏览器本地记住上一次填写的内容。"""
        html = (PROJECT_ROOT / "docs" / "config-wizard.html").read_text(encoding="utf-8")

        for expected in (
            "localStorage",
            "stock-egon-config-wizard-v1",
            "saveDraft",
            "loadDraft",
            "clearSavedDraft",
            "清空本机记忆",
        ):
            self.assertIn(expected, html)


if __name__ == "__main__":
    unittest.main()
