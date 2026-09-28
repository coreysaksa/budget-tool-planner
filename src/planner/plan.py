"""Simple budget planner.

Strategy: fully recognize mandatory needs first, then fund goals, then make the
remaining income available for broad discretionary budgets.
"""
from __future__ import annotations

from .money import ZERO, cents, json_money, money
from .models import BudgetLine, BudgetPlan, Goal

MANDATORY_CATEGORY_ORDER = (
    "housing",
    "utilities_connectivity",
    "food_household",
    "transportation",
    "insurance",
    "healthcare",
    "debt_minimums",
    "family_care",
    "taxes_fees",
    "other_commitments",
)


def build_plan(
    period: str,
    monthly_income: float,
    analysis_by_category: dict[str, float],
    goals: list[Goal],
) -> BudgetPlan:
    income = cents(monthly_income)
    remaining = income

    # 1) Record every mandatory need at its full monthly amount. If income cannot
    # cover them, preserve the full requirement and surface the resulting deficit
    # instead of making the budget look balanced by silently underfunding a bill.
    lines: list[BudgetLine] = []
    for category in MANDATORY_CATEGORY_ORDER:
        required = cents(analysis_by_category.get(category))
        if required <= ZERO:
            continue
        lines.append(
            BudgetLine(
                category=category,
                allocated=json_money(required),
            )
        )
        remaining -= required

    mandatory_shortfall = max(-remaining, ZERO)
    available = max(remaining, ZERO)

    # 2) Fund goals only after all mandatory spending is accounted for.
    goal_contributions: dict[str, float] = {}
    for g in goals:
        contribution = cents(min(money(g.monthly_contribution), available))
        goal_contributions[g.id] = json_money(contribution)
        available -= contribution

    # 3) Whatever is left funds the user's interchangeable discretionary buckets.
    petty_cash = max(available, ZERO)

    return BudgetPlan(
        period=period,
        monthly_income=json_money(income),
        lines=lines,
        petty_cash_allocation=json_money(petty_cash),
        goal_contributions=goal_contributions,
        unallocated=0.0,
        mandatory_shortfall=json_money(mandatory_shortfall),
    )
