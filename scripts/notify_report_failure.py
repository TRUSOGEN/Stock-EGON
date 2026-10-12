#!/usr/bin/env python3
"""工作流失败时向既有邮箱发送健康告警，不包含持仓和模型响应正文。"""

from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from us_stock_agent.notifications import send_email_markdown


def main() -> int:
    """发送固定故障提示并输出可审计状态。"""
    repository = os.environ.get("GITHUB_REPOSITORY", "TRUSOGEN/Stock-EGON")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    url = f"https://github.com/{repository}/actions/runs/{run_id}"
    result = send_email_markdown(
        f"# Stock-EGON 报告未完成\n\n本次报告生成或发送失败，未记录成功送达。请查看运行记录：{url}\n\n不要沿用上一封邮件的价格作为当前行情。",
        subject="Stock-EGON 报告故障提醒",
    )
    print({"failure_alert_sent": result.get("sent"), "skipped": result.get("skipped")})
    return 0 if result.get("sent") else 2


if __name__ == "__main__":
    raise SystemExit(main())
