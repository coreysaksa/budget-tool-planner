"""Simple budget planner.

Strategy (v0): fund goal contributions first, allocate essentials from historical spend,
then set the petty-cash (discretionary checking) allocation from what remains.
"""
from __future__ import annotations

from .money import ZERO, cents, json_money, money
from .models import BudgetLine, BudgetPlan, Goal

# Non-debt "mandatory" categories from the analyzer taxonomy. Debt (credit cards /
# loans) is intentionally excluded here because the payoff scheduler funds it.
ESSENTIAL = {"housing", "utilities", "groceries", "insurance", "healthcare", "transport"}


def build_plan(
    period: str,
    monthly_income: float,
    analysis_by_category: dict[str, float],
    goals: list[Goal],
) -> BudgetPlan:
    income = cents(monthly_income)
    remaining = income
    goal_contributions: dict[str, float] = {}

    # 1) Fund goals.
    for g in goals:
        contribution = cents(
            min(money(g.monthly_contribution), remaining)
        )
        goal_contributions[g.id] = json_money(contribution)
        remaining -= contribution

    # 2) Essentials from historical spend.
    lines: list[BudgetLine] = []
    for category, spent in analysis_by_category.items():
        if category in ESSENTIAL:
            allocated = cents(min(money(spent), remaining))
            lines.append(
                BudgetLine(
                    category=category,
                    allocated=json_money(allocated),
                )
            )
            remaining -= allocated

    # 3) Whatever is left funds discretionary petty cash.
    petty_cash = max(remaining, ZERO)

    return BudgetPlan(
        period=period,
        monthly_income=json_money(income),
        lines=lines,
        petty_cash_allocation=json_money(petty_cash),
        goal_contributions=goal_contributions,
        unallocated=0.0,
    )
