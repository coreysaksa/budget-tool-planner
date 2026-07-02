from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .models import Goal
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
