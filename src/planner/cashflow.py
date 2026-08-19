"""Deterministic paycheck-to-paycheck cash-flow planning."""
from __future__ import annotations

import calendar
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from statistics import median
from typing import Any

from .models import (
    BudgetBaselineItem,
    CashFlowAccount,
    CashFlowPlan,
    CashFlowScenario,
    ClarificationQuestion,
    NecessityOverride,
    PaycheckInput,
    PayPeriodPlan,
    SavingsOpportunity,
    ScheduledCashItem,
    Windfall,
)

_MANDATORY_LEAVES = {
    "mortgage",
    "hoa",
    "rent",
    "student_loan",
    "credit_card_payment",
    "loan_payment",
    "internet",
    "cell_phone",
    "electric",
    "gas_utility",
    "water",
    "groceries",
    "insurance",
    "healthcare",
    "fuel",
    "tolls",
    "transit",
    "user_mandatory",
}
_DINING_LEAVES = {"dining", "coffee", "delivery"}
_SURVIVAL_ROLLUPS = {
    "mortgage": "housing",
    "hoa": "housing",
    "hoa_fees": "housing",
    "house_maintenance": "housing",
    "rent": "housing",
    "car_loans": "transportation",
    "car_payment": "transportation",
    "fuel": "transportation",
    "tolls": "transportation",
    "transit": "transportation",
    "car_subscription": "transportation",
    "internet": "utilities",
    "cell_phone": "utilities",
    "electric": "utilities",
    "gas_utility": "utilities",
    "water": "utilities",
    "groceries": "food_essentials",
    "pet_food": "pets",
    "pet_grooming": "pets",
    "healthcare": "healthcare",
    "insurance": "insurance",
    "student_loan": "debt_obligations",
    "loan_payment": "debt_obligations",
}
_SURVIVAL_ROLLUP_LABELS = {
    "housing": "Housing",
    "transportation": "Transportation",
    "utilities": "Utilities",
    "food_essentials": "Food essentials",
    "pets": "Pet essentials",
    "healthcare": "Healthcare",
    "insurance": "Insurance reserves",
    "debt_obligations": "Other debt obligations",
}


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _roll_up_survival_baseline(
    baseline: list[BudgetBaselineItem],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    for item in baseline:
        key = _SURVIVAL_ROLLUPS.get(item.category, item.category)
        row = grouped.setdefault(
            key,
            {
                "id": f"rollup-{key}",
                "name": _SURVIVAL_ROLLUP_LABELS.get(key, item.name),
                "category": key,
                "monthly_amount": 0.0,
                "source": "confirmed",
                "confidence": "high",
            },
        )
        row["monthly_amount"] += max(0.0, item.monthly_amount)
        if item.source != "confirmed":
            row["source"] = "inferred"
        if confidence_rank.get(item.confidence, 0) < confidence_rank.get(
            row["confidence"], 0
        ):
            row["confidence"] = item.confidence
    for row in grouped.values():
        row["monthly_amount"] = round(row["monthly_amount"], 2)
    return list(grouped.values())


def _month_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(max(day, 1), calendar.monthrange(year, month)[1]))


def _consistent_amounts(amounts: list[float]) -> bool:
    if not amounts:
        return False
    typical = median(amounts)
    return typical > 0 and all(abs(value - typical) <= max(25.0, typical * 0.15) for value in amounts)


def _income_transactions(income_tree: list[dict[str, Any]]) -> dict[str, list[tuple[date, float]]]:
    grouped: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for source in income_tree:
        name = str(source.get("source") or "Income")
        for txn in source.get("transactions") or []:
            when = _parse_date(txn.get("date"))
            amount = float(txn.get("amount") or 0.0)
            if when and amount > 0:
                grouped[name].append((when, amount))
    return grouped


def _infer_paychecks(
    income_tree: list[dict[str, Any]],
    year: int,
    month: int,
    provided: list[PaycheckInput],
) -> tuple[list[ScheduledCashItem], str, str | None]:
    if provided:
        items = [
            ScheduledCashItem(
                name=item.name,
                amount=round(item.amount, 2),
                date=_month_date(year, month, item.day).isoformat(),
                category="paycheck",
            )
            for item in provided
            if item.amount > 0
        ]
        if items:
            description = ", ".join(
                f"{item.name} ${item.amount:,.2f} on day {_parse_date(item.date).day}"
                for item in items
                if _parse_date(item.date)
            )
            return items, "confirmed", description

    best: tuple[int, str, list[tuple[date, float]]] | None = None
    for source, entries in _income_transactions(income_tree).items():
        entries = sorted(entries)
        amounts = [amount for _, amount in entries]
        if len(entries) < 2 or not _consistent_amounts(amounts):
            continue
        score = len(entries)
        if best is None or score > best[0]:
            best = (score, source, entries)
    if best is None:
        return [], "unknown", None

    _, source, entries = best
    typical = round(median(amount for _, amount in entries), 2)
    months: dict[tuple[int, int], list[int]] = defaultdict(list)
    for when, _ in entries:
        months[(when.year, when.month)].append(when.day)
    two_pay_months = [days for days in months.values() if len(days) == 2]

    dates: list[date] = []
    cadence: str | None = None
    confidence = "medium"
    intervals = [(b[0] - a[0]).days for a, b in zip(entries, entries[1:])]
    biweekly = [gap for gap in intervals if 12 <= gap <= 16]
    if len(entries) >= 4 and len(two_pay_months) >= 2:
        early = [day for days in two_pay_months for day in days if day <= 15]
        late = [day for days in two_pay_months for day in days if day > 15]
        if early and late:
            dates = [
                _month_date(year, month, round(median(early))),
                _month_date(year, month, round(median(late))),
            ]
            cadence = "semi-monthly"
            confidence = "high"
    elif len(entries) >= 3 and len(biweekly) >= max(2, len(intervals) - 1):
        cadence = "biweekly"
        confidence = "high"
        cursor = entries[-1][0]
        while cursor.year > year or (cursor.year == year and cursor.month > month):
            cursor -= timedelta(days=14)
        while cursor < date(year, month, 1):
            cursor += timedelta(days=14)
        month_end = _month_date(year, month, 31)
        while cursor <= month_end:
            dates.append(cursor)
            cursor += timedelta(days=14)
    if not dates:
        monthly_intervals = [gap for gap in intervals if 25 <= gap <= 35]
        if len(entries) >= 2 and monthly_intervals:
            cadence = "monthly"
            dates = [_month_date(year, month, round(median(when.day for when, _ in entries)))]

    if not dates or cadence is None:
        return [], "unknown", None
    items = [
        ScheduledCashItem(
            name=source,
            amount=typical,
            date=when.isoformat(),
            category="paycheck",
        )
        for when in sorted(set(dates))
    ]
    return items, confidence, f"{cadence} pay from {source}, about ${typical:,.2f} per deposit"


def _flatten_spending(
    spending_tree: list[dict[str, Any]],
    necessity_overrides: list[NecessityOverride],
) -> tuple[list[dict[str, Any]], float, int, dict[int, float]]:
    txns: list[dict[str, Any]] = []
    dining_spend = 0.0
    dining_count = 0
    mandatory_by_half: dict[int, float] = defaultdict(float)
    overrides = {
        _merchant_key(item.merchant): item.necessity.strip().lower()
        for item in necessity_overrides
        if _merchant_key(item.merchant)
    }
    for bucket in spending_tree:
        bucket_name = str(bucket.get("bucket") or "")
        for category in bucket.get("categories") or []:
            category_name = str(category.get("category") or "")
            for sub in category.get("subcategories") or []:
                leaf = str(sub.get("subcategory") or "")
                for txn in sub.get("transactions") or []:
                    when = _parse_date(txn.get("date"))
                    amount = abs(float(txn.get("amount") or 0.0))
                    if leaf in _DINING_LEAVES:
                        dining_spend += amount
                        dining_count += 1
                    merchant_key = _merchant_key(
                        txn.get("merchant") or txn.get("description")
                    )
                    override = next(
                        (
                            value
                            for key, value in overrides.items()
                            if key in merchant_key or merchant_key in key
                        ),
                        None,
                    )
                    mandatory = (
                        override == "mandatory"
                        or (override is None and bucket_name == "mandatory")
                    )
                    row = {
                        **txn,
                        "date_obj": when,
                        "amount_value": amount,
                        "bucket": bucket_name,
                        "category": category_name,
                        "subcategory": leaf,
                        "mandatory": mandatory,
                    }
                    txns.append(row)
                    if mandatory and when:
                        mandatory_by_half[1 if when.day <= 15 else 2] += amount
    return txns, dining_spend, dining_count, mandatory_by_half


def _merchant_key(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _obligations(
    recurring: list[dict[str, Any]],
    spending_txns: list[dict[str, Any]],
    accounts: list[CashFlowAccount],
    transfers: list[dict[str, Any]],
    year: int,
    month: int,
    assumptions: list[str],
    questions: list[ClarificationQuestion],
    necessity_overrides: list[NecessityOverride],
) -> list[ScheduledCashItem]:
    items: list[ScheduledCashItem] = []
    overrides = {
        _merchant_key(item.merchant): item.necessity.strip().lower()
        for item in necessity_overrides
        if _merchant_key(item.merchant)
    }
    for bill in recurring:
        merchant = str(bill.get("merchant") or "Recurring bill")
        leaf = str(bill.get("category") or "other")
        amount = abs(float(bill.get("typical_amount") or 0.0))
        merchant_key = _merchant_key(merchant)
        necessity = next(
            (
                value
                for key, value in overrides.items()
                if key in merchant_key or merchant_key in key
            ),
            None,
        )
        if necessity == "discretionary":
            continue
        if necessity == "mandatory":
            leaf = "user_mandatory"
        elif leaf == "other":
            questions.append(
                ClarificationQuestion(
                    code="classify-recurring-bill",
                    question=f"Is the recurring {merchant} charge mandatory or discretionary?",
                    context=f"About ${amount:,.2f} per month; its category is ambiguous.",
                    critical=True,
                )
            )
            continue
        if leaf not in _MANDATORY_LEAVES:
            continue
        key = _merchant_key(merchant)
        matching_days = [
            row["date_obj"].day
            for row in spending_txns
            if row["date_obj"]
            and (
                key in _merchant_key(row.get("merchant") or row.get("description"))
                or _merchant_key(row.get("merchant") or row.get("description")) in key
            )
        ]
        if not matching_days:
            due = date(year, month, 1)
            assumptions.append(
                f"Reserved the ${amount:,.2f} {merchant} bill at month start because its "
                "due date is unknown."
            )
            questions.append(
                ClarificationQuestion(
                    code="missing-bill-date",
                    question=f"What day is the {merchant} bill due?",
                    context=f"The amount appears to be about ${amount:,.2f} monthly.",
                    critical=True,
                )
            )
        else:
            due = _month_date(year, month, round(median(matching_days)))
        items.append(
            ScheduledCashItem(
                name=merchant,
                amount=round(amount, 2),
                date=due.isoformat(),
                category=leaf,
            )
        )

    for account in accounts:
        if (
            account.type != "credit"
            or abs(account.balance) <= 0.01
            or not account.minimum_payment
            or account.minimum_payment <= 0
        ):
            continue
        payment_days = [
            when.day
            for transfer in transfers
            if (when := _parse_date(transfer.get("date")))
            and float(transfer.get("amount") or 0.0) > 0
            and _merchant_key(transfer.get("account")) == _merchant_key(account.name)
        ]
        if payment_days:
            due = _month_date(year, month, round(median(payment_days)))
        else:
            due = date(year, month, 1)
            assumptions.append(
                f"Reserved {account.name}'s ${account.minimum_payment:,.2f} minimum at month start "
                "because its due date is unknown."
            )
            questions.append(
                ClarificationQuestion(
                    code="missing-card-due-date",
                    question=f"What day is the minimum payment due for {account.name}?",
                    context=f"Minimum payment: ${account.minimum_payment:,.2f}.",
                    critical=True,
                )
            )
        items.append(
            ScheduledCashItem(
                name=f"{account.name} minimum",
                amount=round(account.minimum_payment, 2),
                date=due.isoformat(),
                category="minimum_debt_payment",
            )
        )
    return items


def _periods(year: int, month: int, as_of: date) -> list[PayPeriodPlan]:
    last = calendar.monthrange(year, month)[1]
    bounds = [(date(year, month, 1), date(year, month, 15)), (date(year, month, 16), date(year, month, last))]
    return [
        PayPeriodPlan(
            label=f"{start.strftime('%b')} {start.day}–{end.day}",
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            current=start <= as_of <= end,
        )
        for start, end in bounds
    ]


def _within(item: ScheduledCashItem, period: PayPeriodPlan) -> bool:
    when = _parse_date(item.date)
    return bool(when and _parse_date(period.start_date) <= when <= _parse_date(period.end_date))


def _required_start(
    period: PayPeriodPlan,
    income: list[ScheduledCashItem],
    obligations: list[ScheduledCashItem],
    essential: float,
    buffer: float,
) -> float:
    start = _parse_date(period.start_date)
    end = _parse_date(period.end_date)
    if not start or not end:
        return round(buffer, 2)
    by_day: dict[date, float] = defaultdict(float)
    for item in income:
        when = _parse_date(item.date)
        if when:
            by_day[when] += item.amount
    for item in obligations:
        when = _parse_date(item.date)
        if when:
            by_day[when] -= item.amount
    daily_essential = essential / ((end - start).days + 1)
    running = 0.0
    minimum = 0.0
    cursor = start
    while cursor <= end:
        running += by_day.get(cursor, 0.0)
        running -= daily_essential
        minimum = min(minimum, running)
        cursor += timedelta(days=1)
    return round(max(buffer, buffer - minimum), 2)


def _scenario(
    name: str,
    include_estimated: bool,
    base_periods: list[PayPeriodPlan],
    paychecks: list[ScheduledCashItem],
    obligations: list[ScheduledCashItem],
    windfalls: list[Windfall],
    essential_by_period: list[float],
    buffer: float,
    checking_balance: float,
    as_of: date,
) -> CashFlowScenario:
    periods = deepcopy(base_periods)
    included = [
        ScheduledCashItem(
            name=windfall.name,
            amount=round(windfall.amount, 2),
            date=windfall.date,
            category="windfall",
            confirmed=windfall.status == "confirmed",
        )
        for windfall in windfalls
        if windfall.status == "confirmed" or include_estimated
    ]
    all_income = paychecks + included
    for index, period in enumerate(periods):
        period.scheduled_income = [item for item in all_income if _within(item, period)]
        period.obligations = [item for item in obligations if _within(item, period)]
        period.essential_allowance = round(essential_by_period[index], 2)
        period.checking_buffer = round(buffer, 2)
        period.required_starting_balance = _required_start(
            period,
            period.scheduled_income,
            period.obligations,
            period.essential_allowance,
            buffer,
        )

    balance = checking_balance
    for index, period in enumerate(periods):
        start = _parse_date(period.start_date)
        end = _parse_date(period.end_date)
        if not start or not end or end < as_of:
            continue
        effective_start = max(start, as_of)
        balance += sum(
            item.amount
            for item in period.scheduled_income
            if (when := _parse_date(item.date)) and when > as_of
        )
        balance -= sum(
            item.amount
            for item in period.obligations
            if (when := _parse_date(item.date)) and when > as_of
        )
        remaining_days = max(
            0,
            (end - effective_start).days
            + (0 if start <= as_of <= end else 1),
        )
        total_days = (end - start).days + 1
        balance -= period.essential_allowance * remaining_days / total_days
        reserve = (
            periods[index + 1].required_starting_balance
            if index + 1 < len(periods)
            else periods[0].required_starting_balance
        )
        period.safe_extra_payment = round(max(0.0, balance - reserve), 2)
        balance -= period.safe_extra_payment

    return CashFlowScenario(
        name=name,
        includes_estimated_windfalls=include_estimated,
        windfall_total=round(sum(item.amount for item in included), 2),
        safe_extra_payment=round(sum(period.safe_extra_payment for period in periods), 2),
        pay_periods=periods,
    )


def build_cash_flow_plan(
    *,
    as_of: date,
    month: str | None,
    accounts: list[CashFlowAccount],
    spending_tree: list[dict[str, Any]],
    income_tree: list[dict[str, Any]],
    recurring: list[dict[str, Any]],
    transfers: list[dict[str, Any]],
    period_days: int,
    windfalls: list[Windfall],
    paychecks: list[PaycheckInput] | None = None,
    necessity_overrides: list[NecessityOverride] | None = None,
    budget_baseline: list[BudgetBaselineItem] | None = None,
    checking_buffer: float = 250.0,
) -> CashFlowPlan:
    """Build survival targets and safe debt-payment capacity for one calendar month."""
    year, mon = (
        (int(part) for part in month.split("-", 1))
        if month
        else (as_of.year, as_of.month)
    )
    plan_month = f"{year:04d}-{mon:02d}"
    checking_balance = round(
        sum(account.balance for account in accounts if account.type == "checking"), 2
    )
    assumptions = [
        "Variable essentials use observed mandatory spending normalized to a 30-day month.",
        "Safe extra payments retain the checking buffer and the next pay period's survival target.",
    ]
    questions: list[ClarificationQuestion] = []
    paychecks, confidence, description = _infer_paychecks(
        income_tree, year, mon, paychecks or []
    )
    if not paychecks:
        questions.append(
            ClarificationQuestion(
                code="missing-pay-schedule",
                question="What are your usual take-home paycheck amounts and deposit dates?",
                context="The transaction history does not show a reliable recurring payroll pattern.",
                critical=True,
            )
        )
    elif confidence not in {"high", "confirmed"}:
        questions.append(
            ClarificationQuestion(
                code="confirm-pay-schedule",
                question="Can you confirm your usual take-home paycheck amount and deposit date?",
                context=f"History suggests {description}, but there are not enough deposits for high confidence.",
                critical=False,
            )
        )

    overrides = necessity_overrides or []
    spending_txns, dining_spend, dining_count, mandatory_by_half = _flatten_spending(
        spending_tree, overrides
    )
    baseline = [item for item in (budget_baseline or []) if item.active]
    obligations = _obligations(
        [] if baseline else recurring,
        spending_txns,
        accounts,
        transfers,
        year,
        mon,
        assumptions,
        questions,
        overrides,
    )
    if baseline:
        for item in baseline:
            if item.kind != "fixed" or item.monthly_amount <= 0:
                continue
            obligations.append(
                ScheduledCashItem(
                    name=item.name,
                    amount=round(item.monthly_amount, 2),
                    date=_month_date(year, mon, item.due_day or 1).isoformat(),
                    category=item.category,
                    confirmed=item.source == "confirmed",
                )
            )
        variable_essential = sum(
            max(0.0, item.monthly_amount)
            for item in baseline
            if item.kind in {"variable", "periodic"}
        )
        assumptions.append(
            "Confirmed budget-baseline items replace transaction averages; periodic items contribute their monthly sinking-fund amount."
        )
    else:
        monthly_mandatory = (
            sum(
                row["amount_value"]
                for row in spending_txns
                if row["mandatory"]
            )
            * 30.0
            / max(period_days, 1)
        )
        fixed_obligations = sum(item.amount for item in obligations)
        variable_essential = max(0.0, monthly_mandatory - fixed_obligations)
    observed_total = mandatory_by_half[1] + mandatory_by_half[2]
    first_ratio = mandatory_by_half[1] / observed_total if observed_total else 0.5
    essential_by_period = [
        round(variable_essential * first_ratio, 2),
        round(variable_essential * (1 - first_ratio), 2),
    ]

    base_periods = _periods(year, mon, as_of)
    recurring_preview = _scenario(
        "Recurring income",
        False,
        base_periods,
        paychecks,
        obligations,
        [],
        essential_by_period,
        max(0.0, checking_buffer),
        0.0,
        date(year, mon, 1) - timedelta(days=1),
    )
    recurring_safe_extra = _scenario(
        "Recurring income",
        False,
        base_periods,
        paychecks,
        obligations,
        [],
        essential_by_period,
        max(0.0, checking_buffer),
        recurring_preview.pay_periods[0].required_starting_balance,
        date(year, mon, 1) - timedelta(days=1),
    ).safe_extra_payment
    scenarios = [
        _scenario(
            "Confirmed income only",
            False,
            base_periods,
            paychecks,
            obligations,
            windfalls,
            essential_by_period,
            max(0.0, checking_buffer),
            checking_balance,
            as_of,
        )
    ]
    if any(w.status == "estimated" for w in windfalls):
        scenarios.append(
            _scenario(
                "Including estimated windfalls",
                True,
                base_periods,
                paychecks,
                obligations,
                windfalls,
                essential_by_period,
                max(0.0, checking_buffer),
                checking_balance,
                as_of,
            )
        )

    opportunities: list[SavingsOpportunity] = []
    monthly_dining_spend = dining_spend * 30.0 / max(period_days, 1)
    monthly_dining_count = round(dining_count * 30.0 / max(period_days, 1))
    if monthly_dining_count > 0 and monthly_dining_spend > 0:
        target = max(0, monthly_dining_count - max(1, round(monthly_dining_count * 0.25)))
        savings = monthly_dining_spend * (monthly_dining_count - target) / monthly_dining_count
        opportunities.append(
            SavingsOpportunity(
                category="dining",
                description=(
                    f"Reduce restaurant, coffee, and delivery visits from about "
                    f"{monthly_dining_count} to {target} per month."
                ),
                current_monthly_spend=round(monthly_dining_spend, 2),
                current_monthly_count=monthly_dining_count,
                target_monthly_count=target,
                potential_monthly_savings=round(savings, 2),
            )
        )

    minimum_to_survive = max(
        (
            period.required_starting_balance
            for scenario in scenarios[:1]
            for period in scenario.pay_periods
        ),
        default=max(0.0, checking_buffer),
    )
    if baseline:
        breakdown = _roll_up_survival_baseline(baseline)
        baseline_ids = {item.id for item in baseline}
        minimum_total = sum(
            account.minimum_payment
            for account in accounts
            if account.type == "credit"
            and abs(account.balance) > 0.01
            and account.minimum_payment
            and account.minimum_payment > 0
        )
        if minimum_total > 0 and "minimum-credit-cards" not in baseline_ids:
            breakdown.append(
                {
                    "id": "minimum-credit-cards",
                    "name": "Credit card minimum payments",
                    "category": "minimum_debt_payment",
                    "monthly_amount": round(minimum_total, 2),
                    "source": "account",
                    "confidence": "high",
                }
            )
    else:
        breakdown = [
            {
                "id": f"obligation-{index}",
                "name": item.name,
                "category": item.category,
                "monthly_amount": round(item.amount, 2),
                "source": "inferred",
                "confidence": "medium",
            }
            for index, item in enumerate(obligations)
        ]
        if variable_essential > 0:
            breakdown.append(
                {
                    "id": "variable-essentials",
                    "name": "Variable essentials",
                    "category": "variable_essentials",
                    "monthly_amount": round(variable_essential, 2),
                    "source": "inferred",
                    "confidence": "low",
                }
            )
    monthly_survival_budget = sum(
        float(item["monthly_amount"]) for item in breakdown
    )
    return CashFlowPlan(
        month=plan_month,
        as_of=as_of.isoformat(),
        checking_balance=checking_balance,
        pay_schedule_confidence=confidence,
        pay_schedule_description=description,
        minimum_to_survive=round(minimum_to_survive, 2),
        monthly_survival_budget=round(monthly_survival_budget, 2),
        survival_budget_breakdown=breakdown,
        recurring_safe_extra_payment=round(recurring_safe_extra, 2),
        scenarios=scenarios,
        savings_opportunities=opportunities,
        assumptions=assumptions,
        clarification_questions=questions,
    )
