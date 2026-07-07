"""组合风险评估。"""

from __future__ import annotations

from .models import PortfolioView


def assess_portfolio_risk(view: PortfolioView, *, risk_profile: str) -> dict[str, object]:
    """评估单票集中度、现金不足和组合持仓数量风险。"""
    concentration_limit = _single_name_limit(risk_profile)
    top_positions = sorted(view.positions, key=lambda item: item.weight, reverse=True)
    top_weight = top_positions[0].weight if top_positions else 0.0
    concentrated = [position.symbol for position in top_positions if position.weight >= concentration_limit]
    cash_limit = 0.03 if risk_profile == "aggressive" else 0.05
    return {
        "risk_profile": risk_profile,
        "concentration": {
            "limit": concentration_limit,
            "top_weight": top_weight,
            "top_symbols": concentrated,
            "alert": bool(concentrated),
        },
        "cash": {
            "cash_weight": view.cash_weight,
            "minimum_preferred": cash_limit,
            "alert": view.cash_weight < cash_limit,
        },
        "diversification": {
            "position_count": len(view.positions),
            "alert": len(view.positions) < 4,
        },
    }


def _single_name_limit(risk_profile: str) -> float:
    """返回单票集中度阈值。"""
    if risk_profile == "aggressive":
        return 0.38
    if risk_profile == "conservative":
        return 0.22
    return 0.3
