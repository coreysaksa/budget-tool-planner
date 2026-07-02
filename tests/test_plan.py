from planner.models import Goal
from planner.plan import build_plan


def test_plan_funds_goals_then_petty_cash():
    goals = [Goal(id="ef", name="Emergency fund", target_amount=12000, monthly_contribution=500)]
    analysis = {"groceries": 400.0, "utilities": 200.0, "dining": 150.0}
    plan = build_plan("2026-07", monthly_income=4000.0, analysis_by_category=analysis, goals=goals)

    assert plan.goal_contributions["ef"] == 500.0
    # essentials funded (groceries + utilities = 600), dining is not essential
    assert {line.category for line in plan.lines} == {"groceries", "utilities"}
    # remaining: 4000 - 500 - 600 = 2900 -> petty cash
    assert plan.petty_cash_allocation == 2900.0
