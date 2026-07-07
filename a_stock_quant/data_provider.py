"""AKShare 数据访问封装。

本模块负责把 AKShare 返回的中文字段标准化为内部字段，并把缺依赖、接口失败、字段缺失
等问题忠实抛出。上层 CLI 会把这些异常转换为结构化 JSON 错误。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd


DAILY_COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "change_pct",
    "涨跌额": "change_amount",
    "换手率": "turnover",
}


def _load_akshare() -> Any:
    """延迟加载 AKShare，并在缺失时给出清晰错误。"""
    try:
        import akshare as ak  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "当前 Python 环境未安装 akshare，请先运行 `pip install akshare --upgrade`。"
        ) from exc
    return ak


def normalize_daily_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """把 AKShare 日线字段标准化为内部字段。"""
    if frame.empty:
        raise ValueError("AKShare 返回了空日线数据。")
    result = frame.rename(columns=DAILY_COLUMN_MAP).copy()
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in result.columns]
    if missing:
        raise ValueError(f"AKShare 日线数据缺少字段: {', '.join(missing)}")
    result["date"] = pd.to_datetime(result["date"])
    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "change_pct",
        "change_amount",
        "turnover",
    ]
    for column in numeric_columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.sort_values("date").reset_index(drop=True)


class AKShareProvider:
    """AKShare 数据源封装。"""

    def __init__(self) -> None:
        """初始化并加载 AKShare。"""
        self.ak = _load_akshare()

    def fetch_stock_history(self, code: str, *, days: int = 250, adjust: str = "qfq") -> pd.DataFrame:
        """抓取单只 A 股日线历史数据。"""
        end = date.today()
        start = end - timedelta(days=max(days * 2, 90))
        frame = self.ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust=adjust,
        )
        return normalize_daily_frame(frame).tail(days).reset_index(drop=True)

    def fetch_spot_candidates(self, *, limit: int = 80) -> list[dict[str, Any]]:
        """从实时行情中取成交额靠前的候选股，供选股模块进一步拉取历史数据。"""
        frame = self.ak.stock_zh_a_spot_em()
        if frame.empty:
            raise ValueError("AKShare 返回了空的 A 股实时行情。")
        rename_map = {
            "代码": "code",
            "名称": "name",
            "最新价": "price",
            "成交量": "volume",
            "成交额": "amount",
            "市盈率-动态": "pe",
            "市净率": "pb",
            "涨跌幅": "change_pct",
        }
        spot = frame.rename(columns=rename_map).copy()
        for column in ("price", "volume", "amount", "pe", "pb", "change_pct"):
            if column in spot.columns:
                spot[column] = pd.to_numeric(spot[column], errors="coerce")
        spot = spot.dropna(subset=["code", "price"]).sort_values("amount", ascending=False)
        candidates: list[dict[str, Any]] = []
        for _, row in spot.head(limit).iterrows():
            candidates.append(
                {
                    "code": str(row["code"]).zfill(6),
                    "name": str(row.get("name") or row["code"]),
                    "pe": _none_if_nan(row.get("pe")),
                    "pb": _none_if_nan(row.get("pb")),
                }
            )
        return candidates

    def enrich_candidates_with_history(self, candidates: list[dict[str, Any]], *, days: int) -> list[dict[str, Any]]:
        """为候选股补充历史数据，单只失败时保留错误并继续处理其他股票。"""
        enriched: list[dict[str, Any]] = []
        for candidate in candidates:
            try:
                candidate = dict(candidate)
                candidate["history"] = self.fetch_stock_history(candidate["code"], days=days)
                enriched.append(candidate)
            except Exception as exc:  # noqa: BLE001
                candidate = dict(candidate)
                candidate["error"] = str(exc)
        return enriched

    def fetch_market_snapshot(self) -> dict[str, Any]:
        """抓取主要指数、市场广度、行业板块和热门个股快照。"""
        indices = _safe_records(self._fetch_indices())
        spot = self.ak.stock_zh_a_spot_em()
        breadth = _compute_breadth(spot)
        boards = _safe_records(self._fetch_industry_boards())
        hot_stocks = _hot_stock_records(spot)
        return {
            "indices": indices,
            "breadth": breadth,
            "boards": boards,
            "hot_stocks": hot_stocks,
        }

    def _fetch_indices(self) -> pd.DataFrame:
        """抓取主要指数行情。"""
        frame = self.ak.stock_zh_index_spot_sina()
        rename_map = {
            "代码": "code",
            "名称": "name",
            "最新价": "price",
            "涨跌幅": "change_pct",
            "成交量": "volume",
            "成交额": "amount",
        }
        result = frame.rename(columns=rename_map).copy()
        wanted = {"上证指数", "深证成指", "创业板指", "科创50"}
        if "name" in result.columns:
            result = result[result["name"].isin(wanted)]
        return result

    def _fetch_industry_boards(self) -> pd.DataFrame:
        """抓取行业板块行情。"""
        frame = self.ak.stock_board_industry_name_em()
        rename_map = {
            "板块名称": "name",
            "涨跌幅": "change_pct",
            "总市值": "market_cap",
            "换手率": "turnover",
            "上涨家数": "advancers",
            "下跌家数": "decliners",
            "领涨股票": "leading_stock",
        }
        result = frame.rename(columns=rename_map).copy()
        if "change_pct" in result.columns:
            result["change_pct"] = pd.to_numeric(result["change_pct"], errors="coerce")
            result = result.sort_values("change_pct", ascending=False)
        return result


def _none_if_nan(value: Any) -> Any:
    """把 NaN 转成 None。"""
    try:
        if pd.isna(value):
            return None
    except TypeError:
        return value
    return value


def _safe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """将 DataFrame 转为 JSON 友好的记录列表。"""
    records: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        records.append({key: _none_if_nan(value) for key, value in record.items()})
    return records


def _compute_breadth(spot: pd.DataFrame) -> dict[str, Any]:
    """从实时行情计算市场广度。"""
    frame = spot.rename(columns={"涨跌幅": "change_pct"}).copy()
    frame["change_pct"] = pd.to_numeric(frame["change_pct"], errors="coerce")
    return {
        "advancers": int((frame["change_pct"] > 0).sum()),
        "decliners": int((frame["change_pct"] < 0).sum()),
        "flat": int((frame["change_pct"] == 0).sum()),
        "limit_up": int((frame["change_pct"] >= 9.8).sum()),
        "limit_down": int((frame["change_pct"] <= -9.8).sum()),
        "advance_decline_ratio": _none_if_nan(
            round((frame["change_pct"] > 0).sum() / max((frame["change_pct"] < 0).sum(), 1), 4)
        ),
    }


def _hot_stock_records(spot: pd.DataFrame) -> list[dict[str, Any]]:
    """返回成交额靠前的热门个股。"""
    rename_map = {
        "代码": "code",
        "名称": "name",
        "最新价": "price",
        "涨跌幅": "change_pct",
        "成交额": "amount",
    }
    frame = spot.rename(columns=rename_map).copy()
    for column in ("price", "change_pct", "amount"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "amount" in frame.columns:
        frame = frame.sort_values("amount", ascending=False)
    columns = [column for column in ("code", "name", "price", "change_pct", "amount") if column in frame.columns]
    return _safe_records(frame[columns].head(10))
