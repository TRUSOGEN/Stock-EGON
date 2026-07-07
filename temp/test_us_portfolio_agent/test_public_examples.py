"""公开示例内容的敏感持仓防回归测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_REAL_HOLDING_SYMBOLS = {"MRVL", "NVDA", "QQQ", "SPCX", "SPY", "TSLA"}


class TestPublicExamples(unittest.TestCase):
    """确保仓库公开示例不再携带用户真实持仓组合。"""

    def test_portfolio_example_uses_synthetic_public_holding(self) -> None:
        """示例持仓文件使用假数量的公开 ticker，不暴露真实组合。"""
        payload = json.loads((PROJECT_ROOT / "config" / "portfolio.example.json").read_text(encoding="utf-8"))
        symbols = {holding["symbol"] for holding in payload["holdings"]}

        self.assertEqual(symbols, {"AAPL", "MSFT"})
        self.assertEqual(payload["cash"], 10000)
        self.assertEqual(payload["risk_profile"], "balanced")

    def test_docs_do_not_embed_user_real_portfolio(self) -> None:
        """文档不能再包含用户真实持仓 ticker 集合。"""
        docs_to_check = [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "docs" / "us-stock-agent-deployment.md",
            PROJECT_ROOT / "docs" / "portfolio-input-template.md",
        ]
        joined = "\n".join(path.read_text(encoding="utf-8") for path in docs_to_check)

        present = {symbol for symbol in USER_REAL_HOLDING_SYMBOLS if symbol in joined}
        self.assertLess(
            len(present),
            3,
            f"公开文档疑似包含真实持仓组合: {sorted(present)}",
        )


if __name__ == "__main__":
    unittest.main()
