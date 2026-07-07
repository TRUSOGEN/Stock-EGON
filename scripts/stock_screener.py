#!/usr/bin/env python3
"""多因子选股 CLI。

脚本先从 AKShare 获取成交额靠前的 A 股候选池，再拉取候选股历史行情计算评分。为了让
全市场筛选可控，默认只处理成交额靠前的候选池，可通过 `--universe-size` 调整。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a_stock_quant.analysis import screen_stocks
from a_stock_quant.data_provider import AKShareProvider
from a_stock_quant.output import make_error_result, make_result, print_json


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="A 股多因子选股")
    parser.add_argument("--top", type=int, default=10, help="返回排名前 N 只股票")
    parser.add_argument("--strategy", default="multi_factor", choices=["technical", "fundamental", "multi_factor"])
    parser.add_argument("--min-price", type=float, default=2.0, help="最低股价过滤")
    parser.add_argument("--max-price", type=float, default=None, help="最高股价过滤")
    parser.add_argument("--min-volume", type=float, default=5000, help="最低成交量过滤")
    parser.add_argument("--days", type=int, default=120, help="每只股票拉取的历史天数")
    parser.add_argument("--universe-size", type=int, default=80, help="成交额候选池大小")
    return parser.parse_args()


def main() -> int:
    """执行多因子选股并打印 JSON。"""
    args = parse_args()
    try:
        provider = AKShareProvider()
        candidates = provider.fetch_spot_candidates(limit=args.universe_size)
        enriched = provider.enrich_candidates_with_history(candidates, days=args.days)
        data = screen_stocks(
            enriched,
            top=args.top,
            strategy=args.strategy,
            min_price=args.min_price,
            max_price=args.max_price,
            min_volume=args.min_volume,
        )
        data["universe_size"] = len(candidates)
        data["history_loaded"] = len(enriched)
        print_json(
            make_result(
                module="stock_screener",
                data=data,
                data_time=None,
                source_api="ak.stock_zh_a_spot_em + ak.stock_zh_a_hist",
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print_json(
            make_error_result(
                module="stock_screener",
                error=str(exc),
                source_api="ak.stock_zh_a_spot_em + ak.stock_zh_a_hist",
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
