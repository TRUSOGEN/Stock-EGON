#!/usr/bin/env python3
"""生成每日美股持仓简报。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a_stock_quant.output import make_error_result, print_json
from us_stock_agent.portfolio import load_portfolio_from_env, load_portfolio_from_file, load_portfolio_from_json
from us_stock_agent.runner import run_report


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="每日美股持仓简报")
    parser.add_argument("--portfolio-json", help="持仓 JSON 字符串")
    parser.add_argument("--portfolio-file", help="持仓 JSON 文件路径")
    return parser.parse_args()


def main() -> int:
    """运行日报。"""
    args = parse_args()
    try:
        if args.portfolio_json:
            portfolio = load_portfolio_from_json(args.portfolio_json)
        elif args.portfolio_file:
            portfolio = load_portfolio_from_file(args.portfolio_file)
        else:
            portfolio = load_portfolio_from_env()
        print_json(run_report(portfolio=portfolio, report_type="daily"))
        return 0
    except Exception as exc:  # noqa: BLE001
        print_json(
            make_error_result(
                module="us_daily_report",
                error=str(exc),
                source_api="yfinance",
                warnings=["免费美股行情源可能延迟、限流或失败；报告仅供研究复盘，不构成投资建议。"],
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
