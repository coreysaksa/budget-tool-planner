from datetime import date

from planner.cashflow_pipeline import (
    CashFlowPlanningInput,
    _build_pay_schedule,
    _build_savings_opportunities,
    _build_spending_profile,
    _build_survival_budget,
    _resolve_period,
)
from planner.money import cents
from planner.models import (
    BudgetBaselineItem,
    CashFlowAccount,
    PaycheckInput,
)


def _request(**overrides):
    values = {
        "as_of": date(2026, 8, 10),
        "month": "2026-08",
        "accounts": [
            CashFlowAccount(
                id="checking",
                name="Checking",
                type="checking",
                balance=1200,
            ),
            CashFlowAccount(
                id="card",
                name="Card",
                type="credit",
                balance=-1000,
                minimum_payment=50,
            ),
        ],
        "spending_tree": [],
        "income_tree": [],
        "recurring": [],
        "transfers": [],
        "period_days": 30,
        "windfalls": [],
        "paychecks": [],
        "necessity_overrides": [],
        "budget_baseline": [],
        "checking_buffer": 300,
    }
    values.update(overrides)
    return CashFlowPlanningInput(**values)


def test_period_and_confirmed_pay_schedule_are_typed_stages():
    request = _request(
        paychecks=[
            PaycheckInput(name="Salary", amount=2500, day=1),
            PaycheckInput(name="Salary", amount=2500, day=16),
        ]
    )
    period = _resolve_period(request)
    questions = []

    schedule = _build_pay_schedule(request, period, questions)

    assert period.label == "2026-08"
    assert schedule.confidence == "confirmed"
    assert [item.date for item in schedule.items] == [
        "2026-08-01",
        "2026-08-16",
    ]
    assert questions == []


def test_survival_budget_uses_active_baseline_and_card_minimum_once():
    request = _request(
        budget_baseline=[
            BudgetBaselineItem(
                id="rent",
                name="Rent",
                category="rent",
                monthly_amount=1800,
                due_day=1,
                source="confirmed",
                confidence="high",
            ),
            BudgetBaselineItem(
                id="fuel",
                name="Fuel",
                category="fuel",
                kind="variable",
                monthly_amount=200,
                source="confirmed",
                confidence="high",
            ),
            BudgetBaselineItem(
                id="inactive",
                name="Old bill",
                category="utilities",
                monthly_amount=100,
                active=False,
            ),
        ]
    )
    period = _resolve_period(request)
    assumptions = []

    survival = _build_survival_budget(
        request,
        period,
        _build_spending_profile(request),
        assumptions,
        [],
    )

    assert [item.name for item in survival.obligations] == [
        "Card minimum",
        "Rent",
    ]
    assert survival.variable_essential == 200
    assert survival.essential_by_period == [100, 100]
    assert survival.monthly_total == 2050
    assert {item["name"] for item in survival.breakdown} == {
        "Housing",
        "Transportation",
        "Credit card minimum payments",
    }
    assert any("budget-baseline" in assumption for assumption in assumptions)


def test_survival_budget_split_reconciles_a_single_cent():
    request = _request(
        accounts=[],
        budget_baseline=[
            BudgetBaselineItem(
                id="variable",
                name="Variable",
                category="groceries",
                kind="variable",
                monthly_amount=0.01,
                source="confirmed",
                confidence="high",
            )
        ],
    )

    survival = _build_survival_budget(
        request,
        _resolve_period(request),
        _build_spending_profile(request),
        [],
        [],
    )

    assert survival.essential_by_period == [cents("0.01"), cents(0)]
    assert sum(survival.essential_by_period) == survival.variable_essential


def test_spending_profile_drives_dining_savings_stage():
    request = _request(
        period_days=60,
        spending_tree=[
            {
                "bucket": "discretionary",
                "categories": [
                    {
                        "category": "dining",
                        "subcategories": [
                            {
                                "subcategory": "dining",
                                "transactions": [
                                    {
                                        "date": f"2026-07-{day:02d}",
                                        "amount": 40,
                                        "description": "Restaurant",
                                    }
                                    for day in (2, 5, 9, 12, 18, 22, 25, 28)
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    )

    profile = _build_spending_profile(request)
    opportunities = _build_savings_opportunities(
        profile,
        request.period_days,
    )

    assert profile.dining_count == 8
    assert profile.dining_spend == 320
    assert len(opportunities) == 1
    assert opportunities[0].current_monthly_count == 4
    assert opportunities[0].potential_monthly_savings == 40
