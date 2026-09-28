from planner.money import cents, json_money, sum_money
from planner.models import Goal
from planner.plan import build_plan


def test_money_rounds_half_up_from_external_floats():
    assert cents(2.675) == cents("2.68")
    assert json_money("10.005") == 10.01


def test_budget_allocations_reconcile_to_income_at_cent_precision():
    plan = build_plan(
        "2026-09",
        monthly_income=100,
        analysis_by_category={"food_household": 10.005},
        goals=[
            Goal(
                id="goal",
                name="Goal",
                monthly_contribution=33.335,
            )
        ],
    )

    allocations = sum_money(
        [
            *plan.goal_contributions.values(),
            *(line.allocated for line in plan.lines),
            plan.petty_cash_allocation,
        ]
    )

    assert plan.goal_contributions == {"goal": 33.34}
    assert plan.lines[0].allocated == 10.01
    assert plan.petty_cash_allocation == 56.65
    assert allocations == cents(plan.monthly_income)
