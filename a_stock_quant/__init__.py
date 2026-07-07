"""A 股量化分析工具包。

本包提供可测试的核心计算逻辑和 AKShare 数据访问封装。CLI 脚本只负责解析参数、
调用这些核心模块并输出统一 JSON，避免把业务规则散落在命令入口里。
"""

__all__ = [
    "analysis",
    "backtesting",
    "data_provider",
    "indicators",
    "output",
]
