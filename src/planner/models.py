from __future__ import annotations

from pydantic import BaseModel, Field


class Goal(BaseModel):
    id: str
    name: str
    target_amount: float
    monthly_contribution: float | None = None


class BudgetLine(BaseModel):
    category: str
    allocated: float


class BudgetPlan(BaseModel):
    period: str
    monthly_income: float
    lines: list[BudgetLine] = Field(default_factory=list)
    petty_cash_allocation: float = 0.0
    goal_contributions: dict[str, float] = Field(default_factory=dict)
    unallocated: float = 0.0
