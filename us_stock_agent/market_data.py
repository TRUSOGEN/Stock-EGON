"""美股行情 provider。

默认 provider 使用 yfinance，但导入发生在运行时。这样测试和无依赖环境仍可使用离线快照
或 mock provider。
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from .models import MarketSnapshot


class MarketDataProvider(Protocol):
    """行情 provider 协议。"""

    def fetch_snapshot(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        """获取 ticker 最新快照。"""

    def fetch_history(self, symbol: str, *, period: str = "6mo") -> pd.DataFrame:
        """获取 ticker 历史行情。"""


class YFinanceProvider:
    """基于 yfinance 的美股行情 provider。"""

    def __init__(self) -> None:
        """延迟导入 yfinance。"""
        try:
            import yfinance as yf  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("当前环境未安装 yfinance，请先安装 requirements.txt。") from exc
        self.yf = yf

    def fetch_snapshot(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        """获取最新价和前收盘价。"""
        snapshots: dict[str, MarketSnapshot] = {}
        for symbol in symbols:
            ticker = self.yf.Ticker(symbol)
            try:
                fast_info = ticker.fast_info
                price = _float_from_fast_info(fast_info, "last_price")
                previous_close = _float_from_fast_info(fast_info, "previous_close")
            except Exception:  # noqa: BLE001
                price = None
                previous_close = None
            if price is None:
                history = self.fetch_history(symbol, period="5d")
                if history.empty:
                    raise ValueError(f"{symbol} 没有可用行情。")
                price = float(history["close"].iloc[-1])
                previous_close = float(history["close"].iloc[-2]) if len(history) >= 2 else None
            snapshots[symbol] = MarketSnapshot(
                symbol=symbol,
                price=price,
                previous_close=previous_close,
                data_time=None,
            )
        return snapshots

    def fetch_history(self, symbol: str, *, period: str = "6mo") -> pd.DataFrame:
        """获取并标准化 yfinance 历史行情。"""
        try:
            frame = self.yf.download(symbol, period=period, auto_adjust=True, progress=False)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"无法通过 yfinance 获取 {symbol} 历史行情: {exc}") from exc
        if frame.empty:
            raise ValueError(f"{symbol} 没有历史行情。")
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame = frame.reset_index().rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        required = ["date", "open", "high", "low", "close", "volume"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"{symbol} 历史行情缺少字段: {', '.join(missing)}")
        return frame[required].dropna().reset_index(drop=True)


def _float_from_fast_info(fast_info: object, key: str) -> float | None:
    """兼容 yfinance fast_info 的 dict/对象访问。"""
    try:
        value = fast_info[key]  # type: ignore[index]
    except Exception:  # noqa: BLE001
        value = getattr(fast_info, key, None)
    if value is None:
        return None
    return float(value)
