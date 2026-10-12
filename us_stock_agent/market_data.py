"""美股行情入口：统一使用最近完整常规交易日、保留来源并拒绝过期价格。

单次 provider 缓存原始日线；快照、指标和邮件图表复用同一数据集。收盘价不进行
股息复权，Yahoo 的 Close 仍按拆股调整；持仓股数和成本必须使用券商当前口径。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Protocol

import pandas as pd
import pandas_market_calendars as mcal

from .models import MarketSnapshot


class MarketDataProvider(Protocol):
    """行情 provider 协议。"""

    def fetch_snapshot(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        """获取最近完整交易日快照。"""

    def fetch_history(self, symbol: str, *, period: str = "6mo") -> pd.DataFrame:
        """获取同口径历史行情。"""


class YFinanceProvider:
    """使用 Yahoo 日线和交易日历校验收盘行情。"""

    def __init__(self) -> None:
        """延迟导入外部数据依赖并建立本次运行缓存。"""
        try:
            import yfinance as yf
        except ModuleNotFoundError as exc:
            raise RuntimeError("当前环境未安装 yfinance，请先安装 requirements.txt。") from exc
        self.yf = yf
        self._histories: dict[tuple[str, str], pd.DataFrame] = {}
        self._metadata: dict[str, dict] = {}

    def fetch_snapshot(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        """从本次日线生成带交易时间的收盘价，避免 fast_info 旧值与盘后混用。"""
        snapshots = {}
        for symbol in symbols:
            history = self.fetch_history(symbol)
            metadata = self._metadata[symbol]
            last = history.iloc[-1]
            data_date = pd.Timestamp(last["date"]).date()
            close_time = latest_completed_session_close()
            if data_date != close_time.date():
                raise ValueError(f"{symbol} 行情过期或交易日不符: {data_date}，应为 {close_time.date()}。")
            quote_time = metadata.get("regularMarketTime")
            reference = metadata.get("regularMarketPrice")
            if quote_time is not None and reference is not None:
                timestamp = _as_timestamp(quote_time)
                if timestamp.date() == data_date and timestamp >= close_time:
                    reference = float(reference)
                    if not isfinite(reference) or reference <= 0 or abs(float(last["close"]) / reference - 1) > 0.005:
                        raise ValueError(f"{symbol} 日线收盘与同交易日常规报价冲突，暂停估值。")
            warnings = []
            if "stock_splits" in history and history["stock_splits"].ne(0).any():
                warnings.append(f"{symbol} 历史区间存在拆股，请核对券商当前股数与每股成本；系统不自动改写持仓。")
            snapshots[symbol] = MarketSnapshot(
                symbol=symbol, price=round(float(last["close"]), 4),
                previous_close=round(float(history["close"].iloc[-2]), 4) if len(history) >= 2 else None,
                name=metadata.get("longName") or metadata.get("shortName"),
                currency=str(metadata["currency"]), data_time=close_time.isoformat(),
                source="Yahoo Finance / yfinance", price_basis="regular_session_close_split_adjusted",
                quality="medium", warnings=tuple(warnings),
            )
        return snapshots

    def fetch_history(self, symbol: str, *, period: str = "6mo") -> pd.DataFrame:
        """标准化非股息复权日线，并排除尚未收盘的当日以及代码复用前历史。"""
        if not hasattr(self, "_histories"):
            self._histories, self._metadata = {}, {}
        key = (symbol, period)
        if key in self._histories:
            return self._histories[key].copy()
        ticker = self.yf.Ticker(symbol)
        try:
            raw = ticker.history(period=period, interval="1d", auto_adjust=False,
                                 actions=True, prepost=False, timeout=15)
            metadata = ticker.history_metadata
        except Exception as exc:
            raise RuntimeError(f"无法通过 yfinance 获取 {symbol} 历史行情（{type(exc).__name__}）。") from exc
        if raw.empty:
            raise ValueError(f"{symbol} 没有历史行情，不能使用旧报价代替。")
        returned_symbol = str(metadata.get("symbol", "")).upper()
        if returned_symbol != symbol.upper():
            raise ValueError(f"行情代码不匹配: 请求 {symbol}，返回 {returned_symbol or '缺失'}。")
        if not metadata.get("currency"):
            raise ValueError(f"{symbol} 行情缺少币种。")
        frame = raw.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume", "Stock Splits": "stock_splits",
        })
        required = ["date", "open", "high", "low", "close", "volume"]
        missing = [column for column in required if column not in frame]
        if missing:
            raise ValueError(f"{symbol} 历史行情缺少字段: {', '.join(missing)}")
        close_time = latest_completed_session_close()
        dates = pd.to_datetime(frame["date"])
        frame = frame.loc[dates.dt.date <= close_time.date()].copy()
        first_trade = metadata.get("firstTradeDate")
        if first_trade is not None:
            first_date = _as_timestamp(first_trade).date()
            frame = frame.loc[pd.to_datetime(frame["date"]).dt.date >= first_date]
        frame = frame.sort_values("date").reset_index(drop=True)
        if frame.empty or frame["date"].duplicated().any():
            raise ValueError(f"{symbol} 无有效已收盘日线或存在重复交易日。")
        values = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
        if not values.map(isfinite).all().all() or (values[["open", "high", "low", "close"]] <= 0).any().any() or (values["volume"] < 0).any():
            raise ValueError(f"{symbol} 历史行情包含缺失、非有限或非法价格/成交量。")
        if ((values["low"] > values[["open", "close"]].min(axis=1)) | (values["high"] < values[["open", "close"]].max(axis=1))).any():
            raise ValueError(f"{symbol} 历史 OHLC 价格关系异常。")
        frame[values.columns] = values
        columns = required + (["stock_splits"] if "stock_splits" in frame else [])
        frame = frame[columns]
        self._metadata[symbol] = dict(metadata)
        self._histories[key] = frame
        return frame.copy()


def latest_completed_session_close(now: datetime | None = None) -> pd.Timestamp:
    """按 NYSE 日历返回已结束的最近常规盘，兼容假日、半日市和夏令时。"""
    timestamp = pd.Timestamp(now or datetime.now(timezone.utc))
    calendar = mcal.get_calendar("NYSE")
    schedule = calendar.schedule(start_date=timestamp.date() - timedelta(days=14), end_date=timestamp.date())
    completed = schedule.loc[schedule["market_close"] <= timestamp]
    if completed.empty:
        raise ValueError("交易日历无法确定最近完整交易日。")
    return completed["market_close"].iloc[-1].tz_convert("America/New_York")


def _as_timestamp(value: object) -> pd.Timestamp:
    """兼容 Yahoo 秒级时间戳与新版 yfinance Timestamp。"""
    timestamp = pd.Timestamp(value, unit="s", tz="UTC") if isinstance(value, (int, float)) else pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("America/New_York")
    return timestamp.tz_convert("America/New_York")
