from __future__ import annotations

from pydantic import BaseModel, Field


class Milestone(BaseModel):
    name: str
    amount: float = 0.0
    due_date: str | None = None
    payment_timing: str = "upfront"
    funded_amount: float = 0.0


class Goal(BaseModel):
    id: str
    name: str
    # Rich fields are optional so simple {id, name, target_amount} goals still
    # validate; the planner only uses monthly_contribution today, but accepting
    # the full shape lets rich goals round-trip without being silently dropped.
    kind: str = "savings"
    target_amount: float | None = None
    target_date: str | None = None
    monthly_contribution: float | None = None
    linked_account: str | None = None
    target_accounts: list[str] = Field(default_factory=list)
    milestones: list[Milestone] = Field(default_factory=list)
    notes: str | None = None


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
