#!/usr/bin/env python3
"""个股诊断 CLI。

脚本从 AKShare 获取指定 A 股历史行情，计算技术指标并输出统一 JSON。外部数据错误会以
`ok=false` 的 JSON 暴露，便于 Codex 或其他自动化流程正确失败。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a_stock_quant.analysis import analyze_stock
from a_stock_quant.data_provider import AKShareProvider
from a_stock_quant.output import make_error_result, make_result, print_json


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="A 股个股技术诊断")
    parser.add_argument("--code", required=True, help="6 位 A 股代码，例如 000001")
    parser.add_argument("--name", default=None, help="股票名称，可选")
    parser.add_argument("--days", type=int, default=250, help="历史数据天数")
    return parser.parse_args()


def main() -> int:
    """执行个股诊断并打印 JSON。"""
    args = parse_args()
    try:
        provider = AKShareProvider()
        history = provider.fetch_stock_history(args.code, days=args.days)
        data = analyze_stock(args.code, args.name or args.code, history)
        print_json(
            make_result(
                module="stock_diagnosis",
                data=data,
                data_time=str(history["date"].iloc[-1])[:10],
                source_api="ak.stock_zh_a_hist",
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print_json(make_error_result(module="stock_diagnosis", error=str(exc), source_api="ak.stock_zh_a_hist"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
