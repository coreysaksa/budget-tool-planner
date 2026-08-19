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


class Windfall(BaseModel):
    name: str
    amount: float
    date: str
    status: str = "estimated"  # "confirmed" | "estimated"


class PaycheckInput(BaseModel):
    name: str = "Paycheck"
    amount: float
    day: int = Field(ge=1, le=31)


class NecessityOverride(BaseModel):
    merchant: str
    necessity: str  # "mandatory" | "discretionary"


class BudgetBaselineItem(BaseModel):
    id: str
    name: str
    category: str
    kind: str = "fixed"  # "fixed" | "variable" | "periodic"
    monthly_amount: float = 0.0
    due_day: int | None = Field(default=None, ge=1, le=31)
    periodic_amount: float | None = None
    frequency_months: int | None = Field(default=None, ge=1)
    next_due_date: str | None = None
    reserved_balance: float = 0.0
    funding_account_id: str | None = None
    review_required: bool = False
    source: str = "inferred"  # "inferred" | "confirmed"
    confidence: str = "low"
    active: bool = True


class SurvivalBudgetItem(BaseModel):
    id: str
    name: str
    category: str
    monthly_amount: float
    source: str
    confidence: str


class CashFlowAccount(BaseModel):
    id: str
    name: str
    type: str
    balance: float = 0.0
    minimum_payment: float | None = None


class ScheduledCashItem(BaseModel):
    name: str
    amount: float
    date: str | None = None
    category: str
    confirmed: bool = True


class PayPeriodPlan(BaseModel):
    label: str
    start_date: str
    end_date: str
    current: bool = False
    required_starting_balance: float = 0.0
    scheduled_income: list[ScheduledCashItem] = Field(default_factory=list)
    obligations: list[ScheduledCashItem] = Field(default_factory=list)
    essential_allowance: float = 0.0
    checking_buffer: float = 0.0
    safe_extra_payment: float = 0.0


class CashFlowScenario(BaseModel):
    name: str
    includes_estimated_windfalls: bool = False
    windfall_total: float = 0.0
    safe_extra_payment: float = 0.0
    pay_periods: list[PayPeriodPlan] = Field(default_factory=list)


class SavingsOpportunity(BaseModel):
    category: str
    description: str
    current_monthly_spend: float
    current_monthly_count: int
    target_monthly_count: int
    potential_monthly_savings: float


class ClarificationQuestion(BaseModel):
    code: str
    question: str
    context: str | None = None
    critical: bool = False


class CashFlowPlan(BaseModel):
    month: str
    as_of: str
    checking_balance: float = 0.0
    pay_schedule_confidence: str = "unknown"
    pay_schedule_description: str | None = None
    minimum_to_survive: float = 0.0
    monthly_survival_budget: float = 0.0
    survival_budget_breakdown: list[SurvivalBudgetItem] = Field(default_factory=list)
    recurring_safe_extra_payment: float = 0.0
    scenarios: list[CashFlowScenario] = Field(default_factory=list)
    savings_opportunities: list[SavingsOpportunity] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
