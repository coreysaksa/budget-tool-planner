from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .cashflow import build_cash_flow_plan
from .models import (
    CashFlowAccount,
    Goal,
    NecessityOverride,
    PaycheckInput,
    Windfall,
)
from .plan import build_plan

app = FastAPI(title="budget-tool-planner")


class PlanRequest(BaseModel):
    period: str
    monthly_income: float
    analysis_by_category: dict[str, float]
    goals: list[Goal]


@app.post("/plan")
def plan_endpoint(req: PlanRequest):
    return build_plan(req.period, req.monthly_income, req.analysis_by_category, req.goals)


class CashFlowPlanRequest(BaseModel):
    as_of: date = Field(default_factory=date.today)
    month: str | None = None
    accounts: list[CashFlowAccount] = Field(default_factory=list)
    spending_tree: list[dict[str, Any]] = Field(default_factory=list)
    income_tree: list[dict[str, Any]] = Field(default_factory=list)
    recurring: list[dict[str, Any]] = Field(default_factory=list)
    transfers: list[dict[str, Any]] = Field(default_factory=list)
    period_days: int = 30
    windfalls: list[Windfall] = Field(default_factory=list)
    paychecks: list[PaycheckInput] = Field(default_factory=list)
    necessity_overrides: list[NecessityOverride] = Field(default_factory=list)
    checking_buffer: float = 250.0


@app.post("/cash-flow-plan")
def cash_flow_plan_endpoint(req: CashFlowPlanRequest):
    return build_cash_flow_plan(
        as_of=req.as_of,
        month=req.month,
        accounts=req.accounts,
        spending_tree=req.spending_tree,
        income_tree=req.income_tree,
        recurring=req.recurring,
        transfers=req.transfers,
        period_days=req.period_days,
        windfalls=req.windfalls,
        paychecks=req.paychecks,
        necessity_overrides=req.necessity_overrides,
        checking_buffer=req.checking_buffer,
    )
