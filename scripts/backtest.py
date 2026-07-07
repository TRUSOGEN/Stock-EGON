#!/usr/bin/env python3
"""策略回测 CLI。

脚本对指定股票运行经典技术策略回测，输出包含假设、区间和风险指标的统一 JSON。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a_stock_quant.backtesting import run_backtest
from a_stock_quant.data_provider import AKShareProvider
from a_stock_quant.output import make_error_result, make_result, print_json


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="A 股经典策略回测")
    parser.add_argument("--code", required=True, help="6 位 A 股代码")
    parser.add_argument("--strategy", default="ma_cross", choices=["ma_cross", "macd", "rsi", "bollinger"])
    parser.add_argument("--days", type=int, default=250, help="回测交易日数量")
    parser.add_argument("--initial-cash", type=float, default=100000, help="初始资金")
    parser.add_argument("--commission", type=float, default=0.0003, help="单边手续费率")
    parser.add_argument("--slippage", type=float, default=0.0005, help="单边滑点率")
    return parser.parse_args()


def main() -> int:
    """执行回测并打印 JSON。"""
    args = parse_args()
    try:
        provider = AKShareProvider()
        history = provider.fetch_stock_history(args.code, days=args.days)
        data = run_backtest(
            history,
            strategy=args.strategy,
            initial_cash=args.initial_cash,
            commission=args.commission,
            slippage=args.slippage,
        )
        data["code"] = args.code
        print_json(
            make_result(
                module="backtest",
                data=data,
                data_time=str(history["date"].iloc[-1])[:10],
                source_api="ak.stock_zh_a_hist",
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print_json(make_error_result(module="backtest", error=str(exc), source_api="ak.stock_zh_a_hist"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
