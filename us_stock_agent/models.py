"""美股持仓 agent 的核心数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Holding:
    """单个持仓条目。"""

    symbol: str
    quantity: float
    cost_basis: float | None = None
    target_weight: float | None = None
    note: str | None = None


@dataclass(frozen=True)
class Portfolio:
    """组合输入配置。"""

    currency: str
    cash: float
    holdings: list[Holding]
    risk_profile: str = "balanced"


@dataclass(frozen=True)
class MarketSnapshot:
    """单个 ticker 的最新行情快照。"""

    symbol: str
    price: float
    previous_close: float | None = None
    name: str | None = None
    currency: str = "USD"
    data_time: str | None = None


@dataclass(frozen=True)
class PositionView:
    """结合持仓和行情后的单票视图。"""

    symbol: str
    quantity: float
    price: float
    market_value: float
    weight: float
    day_change_pct: float | None
    day_pnl: float | None
    unrealized_pnl: float | None
    unrealized_pnl_pct: float | None
    cost_basis: float | None = None
    target_weight: float | None = None


@dataclass(frozen=True)
class PortfolioView:
    """组合层视图。"""

    currency: str
    cash: float
    net_liquidation: float
    invested_value: float
    cash_weight: float
    positions: list[PositionView]


@dataclass(frozen=True)
class PositionScore:
    """单票评分与证据。"""

    symbol: str
    total_score: float
    trend_score: float
    momentum_score: float
    valuation_score: float
    risk_score: float
    concentration_score: float
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ActionRecommendation:
    """研究动作建议。"""

    symbol: str
    action: str
    label: str
    rationale: list[str]
    risk_controls: list[str]
