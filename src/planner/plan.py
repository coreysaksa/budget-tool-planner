"""Simple budget planner.

Strategy (v0): fund goal contributions first, allocate essentials from historical spend,
then set the petty-cash (discretionary checking) allocation from what remains.
"""
from __future__ import annotations

from .models import BudgetLine, BudgetPlan, Goal

ESSENTIAL = {"groceries", "utilities", "mortgage"}


def build_plan(
    period: str,
    monthly_income: float,
    analysis_by_category: dict[str, float],
    goals: list[Goal],
) -> BudgetPlan:
    remaining = monthly_income
    goal_contributions: dict[str, float] = {}

    # 1) Fund goals.
    for g in goals:
        contribution = g.monthly_contribution or 0.0
        contribution = min(contribution, remaining)
        goal_contributions[g.id] = round(contribution, 2)
        remaining -= contribution

    # 2) Essentials from historical spend.
    lines: list[BudgetLine] = []
    for category, spent in analysis_by_category.items():
        if category in ESSENTIAL:
            allocated = min(spent, remaining)
            lines.append(BudgetLine(category=category, allocated=round(allocated, 2)))
            remaining -= allocated

    # 3) Whatever is left funds discretionary petty cash.
    petty_cash = max(remaining, 0.0)

    return BudgetPlan(
        period=period,
        monthly_income=monthly_income,
        lines=lines,
        petty_cash_allocation=round(petty_cash, 2),
        goal_contributions=goal_contributions,
        unallocated=0.0,
    )
