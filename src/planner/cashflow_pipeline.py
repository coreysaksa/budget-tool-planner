"""Typed stages for deterministic paycheck-to-paycheck cash-flow planning."""
from __future__ import annotations

import calendar
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any

from .money import ZERO, cents, json_money, money, sum_money
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
    "hoa_fees",
    "rent",
    "student_loan",
    "credit_card_payment",
    "loan_payment",
    "car_loans",
    "car_maintenance",
    "vehicle_property_tax",
    "property_tax",
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
    "vehicle_registration",
    "childcare",
    "child_support",
    "elder_care",
    "essential_pet_care",
    "professional_license",
    "required_fees",
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
    "car_maintenance": "transportation",
    "vehicle_property_tax": "transportation",
    "vehicle_registration": "transportation",
    "property_tax": "housing",
    "internet": "utilities_connectivity",
    "cell_phone": "utilities_connectivity",
    "electric": "utilities_connectivity",
    "gas_utility": "utilities_connectivity",
    "water": "utilities_connectivity",
    "groceries": "food_household",
    "pet_food": "family_care",
    "pet_grooming": "family_care",
    "essential_pet_care": "family_care",
    "childcare": "family_care",
    "child_support": "family_care",
    "elder_care": "family_care",
    "healthcare": "healthcare",
    "insurance": "insurance",
    "student_loan": "debt_minimums",
    "loan_payment": "debt_minimums",
    "professional_license": "taxes_fees",
    "required_fees": "taxes_fees",
}
_SURVIVAL_ROLLUP_LABELS = {
    "housing": "Housing",
    "transportation": "Transportation",
    "utilities_connectivity": "Utilities & connectivity",
    "food_household": "Food & household essentials",
    "family_care": "Family & care",
    "healthcare": "Healthcare",
    "insurance": "Insurance reserves",
    "debt_minimums": "Debt minimums",
    "taxes_fees": "Taxes & required fees",
}


@dataclass(frozen=True)
class CashFlowPlanningInput:
    as_of: date
    month: str | None
    accounts: list[CashFlowAccount]
    spending_tree: list[dict[str, Any]]
    income_tree: list[dict[str, Any]]
    recurring: list[dict[str, Any]]
    transfers: list[dict[str, Any]]
    period_days: int
    windfalls: list[Windfall]
    paychecks: list[PaycheckInput]
    necessity_overrides: list[NecessityOverride]
    budget_baseline: list[BudgetBaselineItem]
    checking_buffer: float


@dataclass(frozen=True)
class PlanningPeriod:
    year: int
    month: int
    label: str


@dataclass(frozen=True)
class PaySchedule:
    items: list[ScheduledCashItem]
    confidence: str
    description: str | None


@dataclass(frozen=True)
class SpendingProfile:
    transactions: list[dict[str, Any]]
    dining_spend: Decimal
    dining_count: int
    mandatory_by_half: dict[int, Decimal]


@dataclass(frozen=True)
class SurvivalBudget:
    baseline: list[BudgetBaselineItem]
    obligations: list[ScheduledCashItem]
    variable_essential: Decimal
    essential_by_period: list[Decimal]
    breakdown: list[dict[str, Any]]
    monthly_total: Decimal


@dataclass(frozen=True)
class ScenarioPortfolio:
    recurring_safe_extra: Decimal
    scenarios: list[CashFlowScenario]


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
                "monthly_amount": ZERO,
                "source": "confirmed",
                "confidence": "high",
            },
        )
        row["monthly_amount"] += max(ZERO, money(item.monthly_amount))
        if item.source != "confirmed":
            row["source"] = "inferred"
        if confidence_rank.get(item.confidence, 0) < confidence_rank.get(
            row["confidence"], 0
        ):
            row["confidence"] = item.confidence
    for row in grouped.values():
        row["monthly_amount"] = json_money(row["monthly_amount"])
    return list(grouped.values())


def _month_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(max(day, 1), calendar.monthrange(year, month)[1]))


def _consistent_amounts(amounts: list[Decimal]) -> bool:
    if not amounts:
        return False
    typical = median(amounts)
    return typical > ZERO and all(
        abs(value - typical)
        <= max(money(25), typical * money("0.15"))
        for value in amounts
    )


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    current = _month_date(year, month, 31)
    return current - timedelta(days=(current.weekday() - weekday) % 7)


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _us_federal_holidays(year: int) -> set[date]:
    return {
        _observed_fixed_holiday(year, 1, 1),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _last_weekday(year, 5, 0),
        _observed_fixed_holiday(year, 6, 19),
        _observed_fixed_holiday(year, 7, 4),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 10, 0, 2),
        _observed_fixed_holiday(year, 11, 11),
        _nth_weekday(year, 11, 3, 4),
        _observed_fixed_holiday(year, 12, 25),
    }


def _previous_business_day(value: date) -> date:
    holidays = (
        _us_federal_holidays(value.year - 1)
        | _us_federal_holidays(value.year)
        | _us_federal_holidays(value.year + 1)
    )
    current = value
    while current.weekday() >= 5 or current in holidays:
        current -= timedelta(days=1)
    return current


def _scheduled_pay_dates(year: int, month: int) -> tuple[date, date]:
    return (
        _previous_business_day(date(year, month, 15)),
        _previous_business_day(_month_date(year, month, 31)),
    )


def _regular_income_entries(
    entries: list[tuple[date, Decimal]],
) -> list[tuple[date, Decimal]]:
    if len(entries) < 3:
        return entries
    typical = median(amount for _, amount in entries)
    deviations = [abs(amount - typical) for _, amount in entries]
    median_deviation = median(deviations)
    band = max(money(250), typical * money("0.35"), median_deviation * money(3))
    return [
        (when, amount)
        for when, amount in entries
        if abs(amount - typical) <= band
    ]


def _scheduled_semimonthly_pay(
    income_tree: list[dict[str, Any]],
    year: int,
    month: int,
) -> tuple[list[ScheduledCashItem], str, str | None] | None:
    best: tuple[int, str, list[tuple[date, Decimal]]] | None = None
    for source, entries in _income_transactions(
        income_tree,
        payroll_only=True,
    ).items():
        totals_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
        for when, amount in entries:
            totals_by_date[when] += amount
        entries = sorted(totals_by_date.items())
        scheduled_entries: list[tuple[date, Decimal]] = []
        slots: set[str] = set()
        for when, amount in entries:
            mid_month, month_end = _scheduled_pay_dates(when.year, when.month)
            if when == mid_month:
                scheduled_entries.append((when, amount))
                slots.add("mid")
            elif when == month_end:
                scheduled_entries.append((when, amount))
                slots.add("end")
        if slots != {"mid", "end"}:
            continue
        regular_entries = _regular_income_entries(scheduled_entries)
        if len(regular_entries) < 2:
            continue
        score = len(regular_entries)
        if best is None or score > best[0]:
            best = (score, source, regular_entries)
    if best is None:
        return None

    score, source, entries = best
    typical = cents(median(amount for _, amount in entries))
    dates = _scheduled_pay_dates(year, month)
    confidence = "high" if score >= 4 else "medium"
    items = [
        ScheduledCashItem(
            name=source,
            amount=json_money(typical),
            date=when.isoformat(),
            category="paycheck",
        )
        for when in dates
    ]
    return (
        items,
        confidence,
        f"15th and month-end pay from {source}, about ${typical:,.2f} per deposit",
    )


def _income_transactions(
    income_tree: list[dict[str, Any]],
    *,
    payroll_only: bool = False,
) -> dict[str, list[tuple[date, Decimal]]]:
    grouped: dict[str, list[tuple[date, Decimal]]] = defaultdict(list)
    for source in income_tree:
        name = str(source.get("source") or "Income")
        for txn in source.get("transactions") or []:
            if payroll_only:
                payroll_text = " ".join(
                    (
                        name,
                        str(txn.get("merchant") or ""),
                        str(txn.get("description") or ""),
                    )
                ).lower()
                if not any(
                    marker in payroll_text
                    for marker in (
                        "payroll",
                        "salary",
                        "paycheck",
                        "direct deposit",
                        "direct dep",
                        "edipayment",
                    )
                ):
                    continue
            when = _parse_date(txn.get("date"))
            amount = money(txn.get("amount"))
            if when and amount > ZERO:
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
                amount=json_money(item.amount),
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

    scheduled = _scheduled_semimonthly_pay(income_tree, year, month)
    if scheduled is not None:
        return scheduled

    best: tuple[int, str, list[tuple[date, Decimal]]] | None = None
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
    typical = cents(median(amount for _, amount in entries))
    months: dict[tuple[int, int], list[int]] = defaultdict(list)
    for when, _ in entries:
        months[(when.year, when.month)].append(when.day)
    two_pay_months = [days for days in months.values() if len(days) == 2]

    dates: list[date] = []
    cadence: str | None = None
    confidence = "medium"
    intervals = [
        (later[0] - earlier[0]).days
        for earlier, later in zip(entries, entries[1:], strict=False)
    ]
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
            amount=json_money(typical),
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
    dining_spend = ZERO
    dining_count = 0
    mandatory_by_half: dict[int, Decimal] = defaultdict(lambda: ZERO)
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
                    amount = abs(money(txn.get("amount")))
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
        amount = abs(money(bill.get("typical_amount")))
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
                    context=(
                        f"About ${json_money(amount):,.2f} per month; "
                        "its category is ambiguous."
                    ),
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
                f"Reserved the ${json_money(amount):,.2f} {merchant} bill at month start because its "
                "due date is unknown."
            )
            questions.append(
                ClarificationQuestion(
                    code="missing-bill-date",
                    question=f"What day is the {merchant} bill due?",
                    context=(
                        f"The amount appears to be about "
                        f"${json_money(amount):,.2f} monthly."
                    ),
                    critical=True,
                )
            )
        else:
            due = _month_date(year, month, round(median(matching_days)))
        items.append(
            ScheduledCashItem(
                name=merchant,
                amount=json_money(amount),
                date=due.isoformat(),
                category=leaf,
            )
        )

    for account in accounts:
        if (
            account.type != "credit"
            or abs(money(account.balance)) <= money("0.01")
            or not account.minimum_payment
            or account.minimum_payment <= 0
        ):
            continue
        payment_days = [
            when.day
            for transfer in transfers
            if (when := _parse_date(transfer.get("date")))
            and money(transfer.get("amount")) > ZERO
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
                amount=json_money(account.minimum_payment),
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
    essential: Decimal,
    buffer: Decimal,
) -> float:
    start = _parse_date(period.start_date)
    end = _parse_date(period.end_date)
    if not start or not end:
        return json_money(buffer)
    by_day: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for item in income:
        when = _parse_date(item.date)
        if when:
            by_day[when] += money(item.amount)
    for item in obligations:
        when = _parse_date(item.date)
        if when:
            by_day[when] -= money(item.amount)
    daily_essential = essential / money((end - start).days + 1)
    running = ZERO
    minimum = ZERO
    cursor = start
    while cursor <= end:
        running += by_day.get(cursor, ZERO)
        running -= daily_essential
        minimum = min(minimum, running)
        cursor += timedelta(days=1)
    return json_money(max(buffer, buffer - minimum))


def _scenario(
    name: str,
    include_estimated: bool,
    base_periods: list[PayPeriodPlan],
    paychecks: list[ScheduledCashItem],
    obligations: list[ScheduledCashItem],
    windfalls: list[Windfall],
    essential_by_period: list[Decimal],
    buffer: Decimal,
    checking_balance: Decimal,
    as_of: date,
) -> CashFlowScenario:
    periods = deepcopy(base_periods)
    included = [
        ScheduledCashItem(
            name=windfall.name,
            amount=json_money(windfall.amount),
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
        period.essential_allowance = json_money(essential_by_period[index])
        period.checking_buffer = json_money(buffer)
        period.required_starting_balance = _required_start(
            period,
            period.scheduled_income,
            period.obligations,
            essential_by_period[index],
            buffer,
        )

    balance = money(checking_balance)
    for index, period in enumerate(periods):
        start = _parse_date(period.start_date)
        end = _parse_date(period.end_date)
        if not start or not end or end < as_of:
            continue
        effective_start = max(start, as_of)
        balance += sum_money(
            item.amount
            for item in period.scheduled_income
            if (when := _parse_date(item.date)) and when > as_of
        )
        balance -= sum_money(
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
        balance -= (
            money(period.essential_allowance)
            * money(remaining_days)
            / money(total_days)
        )
        reserve = (
            periods[index + 1].required_starting_balance
            if index + 1 < len(periods)
            else periods[0].required_starting_balance
        )
        period.safe_extra_payment = json_money(
            max(ZERO, balance - money(reserve))
        )
        balance -= money(period.safe_extra_payment)

    return CashFlowScenario(
        name=name,
        includes_estimated_windfalls=include_estimated,
        windfall_total=json_money(sum_money(item.amount for item in included)),
        safe_extra_payment=json_money(
            sum_money(period.safe_extra_payment for period in periods)
        ),
        pay_periods=periods,
    )


def execute_cash_flow_pipeline(request: CashFlowPlanningInput) -> CashFlowPlan:
    period = _resolve_period(request)
    assumptions = [
        "Variable essentials use observed mandatory spending normalized to a 30-day month.",
        "Safe extra payments retain the checking buffer and the next pay period's survival target.",
    ]
    questions: list[ClarificationQuestion] = []
    pay_schedule = _build_pay_schedule(request, period, questions)
    spending = _build_spending_profile(request)
    survival = _build_survival_budget(
        request,
        period,
        spending,
        assumptions,
        questions,
    )
    checking_balance = cents(
        sum_money(
            account.balance
            for account in request.accounts
            if account.type == "checking"
        ),
    )
    portfolio = _build_scenario_portfolio(
        request,
        period,
        pay_schedule,
        survival,
        checking_balance,
    )
    opportunities = _build_savings_opportunities(
        spending,
        request.period_days,
    )
    minimum_to_survive = max(
        (
            pay_period.required_starting_balance
            for scenario in portfolio.scenarios[:1]
            for pay_period in scenario.pay_periods
        ),
        default=json_money(max(ZERO, money(request.checking_buffer))),
    )
    return CashFlowPlan(
        month=period.label,
        as_of=request.as_of.isoformat(),
        checking_balance=json_money(checking_balance),
        pay_schedule_confidence=pay_schedule.confidence,
        pay_schedule_description=pay_schedule.description,
        minimum_to_survive=json_money(minimum_to_survive),
        monthly_survival_budget=json_money(survival.monthly_total),
        survival_budget_breakdown=survival.breakdown,
        recurring_safe_extra_payment=json_money(
            portfolio.recurring_safe_extra,
        ),
        scenarios=portfolio.scenarios,
        savings_opportunities=opportunities,
        assumptions=assumptions,
        clarification_questions=questions,
    )


def _resolve_period(request: CashFlowPlanningInput) -> PlanningPeriod:
    year, month = (
        (int(part) for part in request.month.split("-", 1))
        if request.month
        else (request.as_of.year, request.as_of.month)
    )
    return PlanningPeriod(
        year=year,
        month=month,
        label=f"{year:04d}-{month:02d}",
    )


def _build_pay_schedule(
    request: CashFlowPlanningInput,
    period: PlanningPeriod,
    questions: list[ClarificationQuestion],
) -> PaySchedule:
    items, confidence, description = _infer_paychecks(
        request.income_tree,
        period.year,
        period.month,
        request.paychecks,
    )
    if not items:
        questions.append(
            ClarificationQuestion(
                code="missing-pay-schedule",
                question="What are your usual take-home paycheck amounts and deposit dates?",
                context=(
                    "The transaction history does not show a reliable recurring "
                    "payroll pattern."
                ),
                critical=True,
            )
        )
    elif confidence not in {"high", "confirmed"}:
        questions.append(
            ClarificationQuestion(
                code="confirm-pay-schedule",
                question=(
                    "Can you confirm your usual take-home paycheck amount "
                    "and deposit date?"
                ),
                context=(
                    f"History suggests {description}, but there are not enough "
                    "deposits for high confidence."
                ),
                critical=False,
            )
        )
    return PaySchedule(
        items=items,
        confidence=confidence,
        description=description,
    )


def _build_spending_profile(
    request: CashFlowPlanningInput,
) -> SpendingProfile:
    transactions, dining_spend, dining_count, mandatory_by_half = (
        _flatten_spending(
            request.spending_tree,
            request.necessity_overrides,
        )
    )
    return SpendingProfile(
        transactions=transactions,
        dining_spend=dining_spend,
        dining_count=dining_count,
        mandatory_by_half=mandatory_by_half,
    )


def _build_survival_budget(
    request: CashFlowPlanningInput,
    period: PlanningPeriod,
    spending: SpendingProfile,
    assumptions: list[str],
    questions: list[ClarificationQuestion],
) -> SurvivalBudget:
    baseline = [item for item in request.budget_baseline if item.active]
    obligations = _obligations(
        [] if baseline else request.recurring,
        spending.transactions,
        request.accounts,
        request.transfers,
        period.year,
        period.month,
        assumptions,
        questions,
        request.necessity_overrides,
    )
    if baseline:
        obligations.extend(_baseline_obligations(baseline, period))
        variable_essential = sum_money(
            max(ZERO, money(item.monthly_amount))
            for item in baseline
            if item.kind in {"variable", "periodic"}
        )
        assumptions.append(
            "Confirmed budget-baseline items replace transaction averages; "
            "periodic items contribute their monthly sinking-fund amount."
        )
    else:
        monthly_mandatory = (
            sum_money(
                row["amount_value"]
                for row in spending.transactions
                if row["mandatory"]
            )
            * money(30)
            / money(max(request.period_days, 1))
        )
        fixed_obligations = sum_money(item.amount for item in obligations)
        variable_essential = max(
            ZERO,
            monthly_mandatory - fixed_obligations,
        )

    observed_total = (
        spending.mandatory_by_half[1] + spending.mandatory_by_half[2]
    )
    first_ratio = (
        spending.mandatory_by_half[1] / observed_total
        if observed_total
        else money("0.5")
    )
    first_period_essential = cents(variable_essential * first_ratio)
    essential_by_period = [
        first_period_essential,
        cents(variable_essential - first_period_essential),
    ]
    breakdown = _build_survival_breakdown(
        baseline,
        obligations,
        variable_essential,
        request.accounts,
    )
    return SurvivalBudget(
        baseline=baseline,
        obligations=obligations,
        variable_essential=variable_essential,
        essential_by_period=essential_by_period,
        breakdown=breakdown,
        monthly_total=sum_money(item["monthly_amount"] for item in breakdown),
    )


def _baseline_obligations(
    baseline: list[BudgetBaselineItem],
    period: PlanningPeriod,
) -> list[ScheduledCashItem]:
    return [
        ScheduledCashItem(
            name=item.name,
            amount=json_money(item.monthly_amount),
            date=_month_date(
                period.year,
                period.month,
                item.due_day or 1,
            ).isoformat(),
            category=item.category,
            confirmed=item.source == "confirmed",
        )
        for item in baseline
        if item.kind == "fixed" and item.monthly_amount > 0
    ]


def _build_survival_breakdown(
    baseline: list[BudgetBaselineItem],
    obligations: list[ScheduledCashItem],
    variable_essential: float,
    accounts: list[CashFlowAccount],
) -> list[dict[str, Any]]:
    if baseline:
        breakdown = _roll_up_survival_baseline(baseline)
        baseline_ids = {item.id for item in baseline}
        minimum_total = sum_money(
            account.minimum_payment
            for account in accounts
            if account.type == "credit"
            and abs(money(account.balance)) > money("0.01")
            and account.minimum_payment
            and account.minimum_payment > 0
        )
        if minimum_total > ZERO and "minimum-credit-cards" not in baseline_ids:
            breakdown.append(
                {
                    "id": "minimum-credit-cards",
                    "name": "Credit card minimum payments",
                    "category": "minimum_debt_payment",
                    "monthly_amount": json_money(minimum_total),
                    "source": "account",
                    "confidence": "high",
                }
            )
        return breakdown

    breakdown = [
        {
            "id": f"obligation-{index}",
            "name": item.name,
            "category": item.category,
            "monthly_amount": json_money(item.amount),
            "source": "inferred",
            "confidence": "medium",
        }
        for index, item in enumerate(obligations)
    ]
    if variable_essential > ZERO:
        breakdown.append(
            {
                "id": "variable-essentials",
                "name": "Variable essentials",
                "category": "variable_essentials",
                "monthly_amount": json_money(variable_essential),
                "source": "inferred",
                "confidence": "low",
            }
        )
    return breakdown


def _build_scenario_portfolio(
    request: CashFlowPlanningInput,
    period: PlanningPeriod,
    pay_schedule: PaySchedule,
    survival: SurvivalBudget,
    checking_balance: Decimal,
) -> ScenarioPortfolio:
    periods = _periods(period.year, period.month, request.as_of)
    buffer = max(ZERO, money(request.checking_buffer))
    preview_as_of = date(period.year, period.month, 1) - timedelta(days=1)
    recurring_preview = _scenario(
        "Recurring income",
        False,
        periods,
        pay_schedule.items,
        survival.obligations,
        [],
        survival.essential_by_period,
        buffer,
        ZERO,
        preview_as_of,
    )
    recurring_safe_extra = _scenario(
        "Recurring income",
        False,
        periods,
        pay_schedule.items,
        survival.obligations,
        [],
        survival.essential_by_period,
        buffer,
        recurring_preview.pay_periods[0].required_starting_balance,
        preview_as_of,
    ).safe_extra_payment
    scenarios = [
        _scenario(
            "Confirmed income only",
            False,
            periods,
            pay_schedule.items,
            survival.obligations,
            request.windfalls,
            survival.essential_by_period,
            buffer,
            checking_balance,
            request.as_of,
        )
    ]
    if any(windfall.status == "estimated" for windfall in request.windfalls):
        scenarios.append(
            _scenario(
                "Including estimated windfalls",
                True,
                periods,
                pay_schedule.items,
                survival.obligations,
                request.windfalls,
                survival.essential_by_period,
                buffer,
                checking_balance,
                request.as_of,
            )
        )
    return ScenarioPortfolio(
        recurring_safe_extra=recurring_safe_extra,
        scenarios=scenarios,
    )


def _build_savings_opportunities(
    spending: SpendingProfile,
    period_days: int,
) -> list[SavingsOpportunity]:
    monthly_spend = (
        spending.dining_spend
        * money(30)
        / money(max(period_days, 1))
    )
    monthly_count = round(spending.dining_count * 30.0 / max(period_days, 1))
    if monthly_count <= 0 or monthly_spend <= ZERO:
        return []

    target = max(
        0,
        monthly_count - max(1, round(monthly_count * 0.25)),
    )
    savings = (
        monthly_spend
        * money(monthly_count - target)
        / money(monthly_count)
    )
    return [
        SavingsOpportunity(
            category="dining",
            description=(
                "Reduce restaurant, coffee, and delivery visits from about "
                f"{monthly_count} to {target} per month."
            ),
            current_monthly_spend=json_money(monthly_spend),
            current_monthly_count=monthly_count,
            target_monthly_count=target,
            potential_monthly_savings=json_money(savings),
        )
    ]
