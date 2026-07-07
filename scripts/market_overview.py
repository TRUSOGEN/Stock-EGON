#!/usr/bin/env python3
"""大盘与板块概览 CLI。

脚本通过 AKShare 获取主要指数、市场广度、行业板块和热门个股快照，输出统一 JSON。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a_stock_quant.analysis import summarize_market
from a_stock_quant.data_provider import AKShareProvider
from a_stock_quant.output import make_error_result, make_result, print_json


def main() -> int:
    """执行市场概览并打印 JSON。"""
    try:
        provider = AKShareProvider()
        snapshot = provider.fetch_market_snapshot()
        data = summarize_market(
            indices=snapshot["indices"],
            breadth=snapshot["breadth"],
            boards=snapshot["boards"],
            hot_stocks=snapshot["hot_stocks"],
        )
        print_json(
            make_result(
                module="market_overview",
                data=data,
                data_time=None,
                source_api="ak.stock_zh_index_spot_sina + ak.stock_zh_a_spot_em + ak.stock_board_industry_name_em",
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print_json(
            make_error_result(
                module="market_overview",
                error=str(exc),
                source_api="ak.stock_zh_index_spot_sina + ak.stock_zh_a_spot_em + ak.stock_board_industry_name_em",
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
