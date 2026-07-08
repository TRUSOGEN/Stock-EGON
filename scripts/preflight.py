#!/usr/bin/env python3
"""检查 GitHub Actions 运行前的关键配置。

脚本只验证本地环境变量是否结构完整，不会访问网络，也不会打印任何 secret 的原值。
它适合在本地终端或 GitHub Actions 里先跑一遍，提前发现持仓 JSON、邮箱、LLM、
新闻源和正文内嵌图表开关中的结构性问题。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a_stock_quant.output import print_json
from us_stock_agent.preflight import build_preflight_report


def main() -> int:
    """执行预检并以 JSON 输出结果。"""
    report = build_preflight_report(dict(os.environ))
    print_json(report)
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
