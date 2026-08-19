from datetime import date

from planner.cashflow import build_cash_flow_plan
from planner.models import (
    BudgetBaselineItem,
    CashFlowAccount,
    NecessityOverride,
    PaycheckInput,
    Windfall,
)


def _income_tree():
    return [
        {
            "source": "ACME PAYROLL",
            "transactions": [
                {"date": "2026-06-01", "amount": 2500},
                {"date": "2026-06-16", "amount": 2500},
                {"date": "2026-07-01", "amount": 2500},
                {"date": "2026-07-16", "amount": 2500},
                {"date": "2026-08-01", "amount": 2500},
                {"date": "2026-08-16", "amount": 2500},
            ],
        }
    ]


def _spending_tree():
    return [
        {
            "bucket": "mandatory",
            "categories": [
                {
                    "category": "housing",
                    "subcategories": [
                        {
                            "subcategory": "mortgage",
                            "transactions": [
                                {
                                    "date": "2026-06-03",
                                    "amount": 1500,
                                    "description": "Home Mortgage",
                                    "merchant": "Home Mortgage",
                                },
                                {
                                    "date": "2026-07-03",
                                    "amount": 1500,
                                    "description": "Home Mortgage",
                                    "merchant": "Home Mortgage",
                                },
                            ],
                        }
                    ],
                },
                {
                    "category": "groceries",
                    "subcategories": [
                        {
                            "subcategory": "groceries",
                            "transactions": [
                                {"date": "2026-07-07", "amount": 200, "description": "Market"},
                                {"date": "2026-07-21", "amount": 200, "description": "Market"},
                            ],
                        }
                    ],
                },
            ],
        },
        {
            "bucket": "discretionary",
            "categories": [
                {
                    "category": "dining",
                    "subcategories": [
                        {
                            "subcategory": "dining",
                            "transactions": [
                                {"date": f"2026-07-{day:02d}", "amount": 40, "description": "Restaurant"}
                                for day in (2, 5, 9, 12, 18, 22, 25, 28)
                            ],
                        }
                    ],
                }
            ],
        },
    ]


def _plan(*, income=True, windfalls=None):
    return build_cash_flow_plan(
        as_of=date(2026, 8, 10),
        month="2026-08",
        accounts=[
            CashFlowAccount(id="checking", name="Checking", type="checking", balance=1800),
            CashFlowAccount(
                id="card", name="Rewards Card", type="credit", balance=-3000, minimum_payment=75
            ),
        ],
        spending_tree=_spending_tree(),
        income_tree=_income_tree() if income else [],
        recurring=[
            {
                "merchant": "Home Mortgage",
                "category": "mortgage",
                "typical_amount": 1500,
            }
        ],
        transfers=[],
        period_days=60,
        windfalls=windfalls or [],
        paychecks=[],
        necessity_overrides=[],
        checking_buffer=300,
    )


def test_regular_semi_monthly_pay_and_survival_targets():
    plan = _plan()
    assert plan.pay_schedule_confidence == "high"
    periods = plan.scenarios[0].pay_periods
    assert [p.start_date for p in periods] == ["2026-08-01", "2026-08-16"]
    assert periods[0].scheduled_income[0].amount == 2500
    assert periods[0].required_starting_balance >= 300
    assert periods[1].required_starting_balance >= 300
    assert plan.recurring_safe_extra_payment >= 0


def test_missing_pay_schedule_requests_focused_clarification():
    plan = _plan(income=False)
    question = next(q for q in plan.clarification_questions if q.code == "missing-pay-schedule")
    assert question.critical is True
    assert plan.pay_schedule_confidence == "unknown"


def test_low_confidence_pay_schedule_requests_confirmation():
    limited_income = [
        {
            "source": "ACME PAYROLL",
            "transactions": [
                {"date": "2026-06-30", "amount": 2500},
                {"date": "2026-07-31", "amount": 2500},
            ],
        }
    ]
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 10),
        month=None,
        accounts=[CashFlowAccount(id="checking", name="Checking", type="checking", balance=500)],
        spending_tree=[],
        income_tree=limited_income,
        recurring=[],
        transfers=[],
        period_days=90,
        windfalls=[],
        paychecks=[],
        necessity_overrides=[],
    )
    assert plan.month == "2026-08"
    assert plan.pay_schedule_confidence == "medium"
    assert any(q.code == "confirm-pay-schedule" for q in plan.clarification_questions)


def test_mandatory_and_discretionary_classification_and_restaurant_savings():
    plan = _plan()
    first = plan.scenarios[0].pay_periods[0]
    assert any(item.category == "mortgage" for item in first.obligations)
    opportunity = plan.savings_opportunities[0]
    assert opportunity.category == "dining"
    assert opportunity.current_monthly_count == 4
    assert opportunity.potential_monthly_savings == 40


def test_confirmed_and_estimated_windfalls_create_two_scenarios():
    plan = _plan(
        windfalls=[
            Windfall(name="Bonus", amount=1000, date="2026-08-14", status="confirmed"),
            Windfall(
                name="Security-clearance allowance",
                amount=1500,
                date="2026-08-20",
                status="estimated",
            ),
        ]
    )
    assert len(plan.scenarios) == 2
    assert plan.scenarios[0].windfall_total == 1000
    assert plan.scenarios[1].windfall_total == 2500
    assert plan.scenarios[1].safe_extra_payment >= plan.scenarios[0].safe_extra_payment


def test_safe_debt_payment_preserves_buffer_and_minimums():
    plan = _plan()
    scenario = plan.scenarios[0]
    assert any(
        item.category == "minimum_debt_payment"
        for period in scenario.pay_periods
        for item in period.obligations
    )
    assert all(period.safe_extra_payment >= 0 for period in scenario.pay_periods)
    assert scenario.safe_extra_payment < 1800 + 2500


def test_ambiguous_recurring_charge_requests_classification():
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 10),
        month=None,
        accounts=[CashFlowAccount(id="checking", name="Checking", type="checking", balance=500)],
        spending_tree=[],
        income_tree=_income_tree(),
        recurring=[{"merchant": "Mystery Club", "category": "other", "typical_amount": 90}],
        transfers=[],
        period_days=90,
        windfalls=[],
        paychecks=[],
        necessity_overrides=[],
    )
    question = next(
        item for item in plan.clarification_questions if item.code == "classify-recurring-bill"
    )
    assert question.critical is True
    assert "mandatory or discretionary" in question.question


def test_user_provided_pay_schedule_replaces_missing_inference():
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 10),
        month="2026-08",
        accounts=[CashFlowAccount(id="checking", name="Checking", type="checking", balance=500)],
        spending_tree=[],
        income_tree=[],
        recurring=[],
        transfers=[],
        period_days=30,
        windfalls=[],
        paychecks=[
            PaycheckInput(name="Salary", amount=2500, day=1),
            PaycheckInput(name="Salary", amount=2500, day=16),
        ],
        necessity_overrides=[],
    )
    assert plan.pay_schedule_confidence == "confirmed"
    assert not any(q.code == "missing-pay-schedule" for q in plan.clarification_questions)
    assert [item.date for item in plan.scenarios[0].pay_periods[0].scheduled_income] == [
        "2026-08-01"
    ]


def test_user_necessity_override_resolves_ambiguous_bill():
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 10),
        month="2026-08",
        accounts=[CashFlowAccount(id="checking", name="Checking", type="checking", balance=500)],
        spending_tree=[],
        income_tree=_income_tree(),
        recurring=[{"merchant": "Mystery Club", "category": "other", "typical_amount": 90}],
        transfers=[],
        period_days=90,
        windfalls=[],
        paychecks=[],
        necessity_overrides=[
            NecessityOverride(merchant="Mystery Club", necessity="mandatory")
        ],
    )
    assert not any(
        q.code == "classify-recurring-bill" for q in plan.clarification_questions
    )
    assert any(
        item.name == "Mystery Club"
        for period in plan.scenarios[0].pay_periods
        for item in period.obligations
    )


def test_confirmed_baseline_replaces_transaction_average():
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 10),
        month="2026-08",
        accounts=[
            CashFlowAccount(id="checking", name="Checking", type="checking", balance=500),
            CashFlowAccount(
                id="card",
                name="Rewards Card",
                type="credit",
                balance=-3000,
                minimum_payment=75,
            ),
            CashFlowAccount(
                id="card-2",
                name="Travel Card",
                type="credit",
                balance=-1200,
                minimum_payment=40,
            ),
        ],
        spending_tree=_spending_tree(),
        income_tree=_income_tree(),
        recurring=[],
        transfers=[],
        period_days=60,
        windfalls=[],
        budget_baseline=[
            BudgetBaselineItem(
                id="mortgage-primary",
                name="Primary mortgage",
                category="mortgage",
                kind="fixed",
                monthly_amount=1844,
                due_day=1,
                source="confirmed",
                confidence="high",
            ),
            BudgetBaselineItem(
                id="mortgage-second",
                name="Second mortgage",
                category="mortgage",
                kind="fixed",
                monthly_amount=750,
                due_day=15,
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
        ],
    )

    assert plan.monthly_survival_budget == 2909
    assert {item.name for item in plan.survival_budget_breakdown} >= {
        "Housing",
        "Transportation",
        "Credit card minimum payments",
    }
    housing = next(
        item
        for item in plan.survival_budget_breakdown
        if item.category == "housing"
    )
    transportation = next(
        item
        for item in plan.survival_budget_breakdown
        if item.category == "transportation"
    )
    assert housing.monthly_amount == 2594
    assert transportation.monthly_amount == 200
    minimums = next(
        item
        for item in plan.survival_budget_breakdown
        if item.category == "minimum_debt_payment"
    )
    assert minimums.monthly_amount == 115


def test_periodic_baseline_contribution_and_card_minimum_are_counted_once():
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 16),
        month="2026-08",
        accounts=[
            CashFlowAccount(id="checking", name="Checking", type="checking", balance=500),
            CashFlowAccount(
                id="card",
                name="Rewards Card",
                type="credit",
                balance=-3000,
                minimum_payment=75,
            ),
        ],
        spending_tree=[],
        income_tree=_income_tree(),
        recurring=[],
        transfers=[
            {
                "date": "2026-08-10",
                "amount": 5000,
                "category": "credit card payment",
                "role": "debt_service_cash_outflow",
            }
        ],
        period_days=30,
        windfalls=[],
        budget_baseline=[
            BudgetBaselineItem(
                id="insurance",
                name="Car insurance reserve",
                category="insurance",
                kind="periodic",
                monthly_amount=92.50,
                periodic_amount=555,
                frequency_months=6,
                source="confirmed",
                confidence="high",
            )
        ],
    )

    assert plan.monthly_survival_budget == 167.50
    assert {item.name for item in plan.survival_budget_breakdown} == {
        "Insurance reserves",
        "Credit card minimum payments",
    }


def test_survival_breakdown_rolls_all_mandatory_housing_and_transportation():
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 16),
        month="2026-08",
        accounts=[],
        spending_tree=[],
        income_tree=_income_tree(),
        recurring=[],
        transfers=[],
        period_days=30,
        windfalls=[],
        budget_baseline=[
            BudgetBaselineItem(
                id=category,
                name=category,
                category=category,
                monthly_amount=amount,
                source="inferred",
                confidence="medium",
            )
            for category, amount in (
                ("mortgage", 2630.31),
                ("hoa_fees", 522.95),
                ("house_maintenance", 204.16),
                ("car_loans", 691.37),
                ("fuel", 180),
                ("tolls", 262.50),
                ("car_subscription", 9.99),
            )
        ],
    )

    rollups = {
        item.category: item.monthly_amount
        for item in plan.survival_budget_breakdown
    }
    assert rollups["housing"] == 3357.42
    assert rollups["transportation"] == 1143.86
    assert plan.monthly_survival_budget == 4501.28


def test_zero_balance_card_minimum_is_not_in_survival_budget():
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 16),
        month="2026-08",
        accounts=[
            CashFlowAccount(id="checking", name="Checking", type="checking", balance=500),
            CashFlowAccount(
                id="card",
                name="Paid Card",
                type="credit",
                balance=0,
                minimum_payment=75,
            ),
        ],
        spending_tree=[],
        income_tree=_income_tree(),
        recurring=[],
        transfers=[],
        period_days=30,
        windfalls=[],
        budget_baseline=[],
    )

    assert plan.monthly_survival_budget == 0
    assert not any("Paid Card" in item.name for item in plan.survival_budget_breakdown)


def test_same_day_paycheck_is_not_added_to_live_checking_balance_again():
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 16),
        month="2026-08",
        accounts=[
            CashFlowAccount(
                id="checking", name="Checking", type="checking", balance=2800
            )
        ],
        spending_tree=[],
        income_tree=[],
        recurring=[],
        transfers=[],
        period_days=30,
        windfalls=[],
        paychecks=[
            PaycheckInput(name="Salary", amount=2500, day=1),
            PaycheckInput(name="Salary", amount=2500, day=16),
        ],
        necessity_overrides=[],
        checking_buffer=300,
    )
    assert plan.scenarios[0].safe_extra_payment == 2500


def test_weekly_income_is_not_inferred_as_semi_monthly():
    weekly = [
        {
            "source": "WEEKLY PAYROLL",
            "transactions": [
                {"date": "2026-06-05", "amount": 1000},
                {"date": "2026-06-12", "amount": 1000},
                {"date": "2026-06-19", "amount": 1000},
                {"date": "2026-06-26", "amount": 1000},
                {"date": "2026-07-03", "amount": 1000},
                {"date": "2026-07-10", "amount": 1000},
                {"date": "2026-07-17", "amount": 1000},
                {"date": "2026-07-24", "amount": 1000},
            ],
        }
    ]
    plan = build_cash_flow_plan(
        as_of=date(2026, 8, 1),
        month="2026-08",
        accounts=[
            CashFlowAccount(id="checking", name="Checking", type="checking", balance=500)
        ],
        spending_tree=[],
        income_tree=weekly,
        recurring=[],
        transfers=[],
        period_days=60,
        windfalls=[],
        paychecks=[],
        necessity_overrides=[],
    )
    assert plan.pay_schedule_confidence == "unknown"
    assert any(q.code == "missing-pay-schedule" for q in plan.clarification_questions)
