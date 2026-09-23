"""Centralized money arithmetic for planner calculations."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value: Any) -> Decimal:
    """Convert an external numeric value without importing binary-float noise."""
    if value is None:
        return ZERO
    return Decimal(str(value))


def cents(value: Any) -> Decimal:
    return money(value).quantize(CENT, rounding=ROUND_HALF_UP)


def sum_money(values: Iterable[Any]) -> Decimal:
    return sum((money(value) for value in values), start=ZERO)


def json_money(value: Any) -> float:
    """Quantize at the response boundary while preserving JSON number fields."""
    return float(cents(value))
