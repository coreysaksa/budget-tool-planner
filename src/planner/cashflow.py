"""Public cash-flow planning API."""

from __future__ import annotations

from datetime import date
from typing import Any

from .cashflow_pipeline import (
    _MANDATORY_LEAVES,
    CashFlowPlanningInput,
    execute_cash_flow_pipeline,
)
from .models import (
    BudgetBaselineItem,
    CashFlowAccount,
    CashFlowPlan,
    NecessityOverride,
    PaycheckInput,
    Windfall,
)

__all__ = ["_MANDATORY_LEAVES", "build_cash_flow_plan"]


def build_cash_flow_plan(
    *,
    as_of: date,
    month: str | None,
    accounts: list[CashFlowAccount],
    spending_tree: list[dict[str, Any]],
    income_tree: list[dict[str, Any]],
    recurring: list[dict[str, Any]],
    transfers: list[dict[str, Any]],
    period_days: int,
    windfalls: list[Windfall],
    paychecks: list[PaycheckInput] | None = None,
    necessity_overrides: list[NecessityOverride] | None = None,
    budget_baseline: list[BudgetBaselineItem] | None = None,
    checking_buffer: float = 250.0,
) -> CashFlowPlan:
    """Build survival targets and safe debt-payment capacity for one calendar month."""
    return execute_cash_flow_pipeline(
        CashFlowPlanningInput(
            as_of=as_of,
            month=month,
            accounts=accounts,
            spending_tree=spending_tree,
            income_tree=income_tree,
            recurring=recurring,
            transfers=transfers,
            period_days=period_days,
            windfalls=windfalls,
            paychecks=paychecks or [],
            necessity_overrides=necessity_overrides or [],
            budget_baseline=budget_baseline or [],
            checking_buffer=checking_buffer,
        )
    )
