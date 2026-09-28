from planner.models import Goal
from planner.plan import build_plan


def test_plan_funds_mandatory_spending_before_goals_and_petty_cash():
    goals = [Goal(id="ef", name="Emergency fund", target_amount=12000, monthly_contribution=500)]
    analysis = {
        "food_household": 400.0,
        "utilities_connectivity": 200.0,
        "dining_convenience": 150.0,
        "debt_minimums": 75.0,
    }
    plan = build_plan("2026-07", monthly_income=4000.0, analysis_by_category=analysis, goals=goals)

    assert plan.goal_contributions["ef"] == 500.0
    assert {line.category for line in plan.lines} == {
        "food_household",
        "utilities_connectivity",
        "debt_minimums",
    }
    assert plan.petty_cash_allocation == 2825.0
    assert plan.mandatory_shortfall == 0.0


def test_plan_preserves_full_mandatory_need_and_reports_shortfall():
    goals = [Goal(id="trip", name="Trip", monthly_contribution=200)]
    plan = build_plan(
        "2026-09",
        monthly_income=1000,
        analysis_by_category={
            "housing": 900,
            "food_household": 300,
            "entertainment": 100,
        },
        goals=goals,
    )

    assert [(line.category, line.allocated) for line in plan.lines] == [
        ("housing", 900.0),
        ("food_household", 300.0),
    ]
    assert plan.mandatory_shortfall == 200.0
    assert plan.goal_contributions == {"trip": 0.0}
    assert plan.petty_cash_allocation == 0.0
