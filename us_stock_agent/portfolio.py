"""持仓解析和组合视图计算。"""

from __future__ import annotations

import json
import os
from typing import Any

from .models import Holding, MarketSnapshot, Portfolio, PortfolioView, PositionView


def load_portfolio_from_dict(payload: dict[str, Any]) -> Portfolio:
    """从字典加载并校验持仓配置。"""
    holdings_payload = payload.get("holdings")
    if not isinstance(holdings_payload, list) or not holdings_payload:
        raise ValueError("portfolio 配置必须包含非空 holdings 列表。")
    holdings: list[Holding] = []
    for item in holdings_payload:
        symbol = str(item["symbol"]).upper().strip()
        quantity = float(item["quantity"])
        if quantity <= 0:
            raise ValueError(f"{symbol} 的 quantity 必须大于 0。")
        holdings.append(
            Holding(
                symbol=symbol,
                quantity=quantity,
                cost_basis=_optional_float(item.get("cost_basis")),
                target_weight=_optional_float(item.get("target_weight")),
                note=item.get("note"),
            )
        )
    return Portfolio(
        currency=str(payload.get("currency", "USD")).upper(),
        cash=float(payload.get("cash", 0)),
        risk_profile=str(payload.get("risk_profile", "balanced")),
        holdings=holdings,
    )


def load_portfolio_from_json(value: str) -> Portfolio:
    """从 JSON 字符串加载持仓。"""
    return load_portfolio_from_dict(json.loads(value))


def load_portfolio_from_file(path: str) -> Portfolio:
    """从 JSON 文件加载持仓。"""
    with open(path, "r", encoding="utf-8") as file:
        return load_portfolio_from_dict(json.load(file))


def load_portfolio_from_env(env_name: str = "PORTFOLIO_JSON") -> Portfolio:
    """从环境变量加载持仓。"""
    value = os.environ.get(env_name)
    if not value:
        raise ValueError(f"环境变量 {env_name} 未配置。")
    return load_portfolio_from_json(value)


def build_portfolio_view(
    portfolio: Portfolio,
    snapshots: dict[str, MarketSnapshot],
) -> PortfolioView:
    """结合最新行情生成组合视图。"""
    position_values: list[tuple[Holding, MarketSnapshot, float]] = []
    invested_value = 0.0
    for holding in portfolio.holdings:
        snapshot = snapshots.get(holding.symbol)
        if snapshot is None:
            raise ValueError(f"缺少 {holding.symbol} 的行情快照。")
        market_value = holding.quantity * snapshot.price
        invested_value += market_value
        position_values.append((holding, snapshot, market_value))
    net_liquidation = invested_value + portfolio.cash
    if net_liquidation <= 0:
        raise ValueError("组合净资产必须大于 0。")

    positions: list[PositionView] = []
    for holding, snapshot, market_value in position_values:
        day_change_pct = None
        day_pnl = None
        if snapshot.previous_close and snapshot.previous_close > 0:
            day_change_pct = snapshot.price / snapshot.previous_close - 1
            day_pnl = (snapshot.price - snapshot.previous_close) * holding.quantity
        unrealized_pnl = None
        unrealized_pnl_pct = None
        if holding.cost_basis and holding.cost_basis > 0:
            unrealized_pnl = (snapshot.price - holding.cost_basis) * holding.quantity
            unrealized_pnl_pct = snapshot.price / holding.cost_basis - 1
        positions.append(
            PositionView(
                symbol=holding.symbol,
                quantity=holding.quantity,
                price=snapshot.price,
                market_value=market_value,
                weight=market_value / net_liquidation,
                day_change_pct=day_change_pct,
                day_pnl=day_pnl,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                cost_basis=holding.cost_basis,
                target_weight=holding.target_weight,
            )
        )
    positions.sort(key=lambda item: item.market_value, reverse=True)
    return PortfolioView(
        currency=portfolio.currency,
        cash=portfolio.cash,
        net_liquidation=net_liquidation,
        invested_value=invested_value,
        cash_weight=portfolio.cash / net_liquidation,
        positions=positions,
    )


def _optional_float(value: Any) -> float | None:
    """把可选字段转成 float。"""
    if value is None or value == "":
        return None
    return float(value)
