"""Deterministic cash-flow forecasting primitives for CashPilot.

No network calls, no model training, and no persistence. All monetary values are
integer paise. This module is safe to integrate after tenant authorization exists.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


@dataclass(frozen=True)
class ScheduledCash:
    due_date: date
    amount_paise: int
    direction: str  # "in" or "out"
    label: str = ""

    def __post_init__(self):
        if self.amount_paise < 0:
            raise ValueError("amount_paise must not be negative")
        if self.direction not in ("in", "out"):
            raise ValueError("direction must be 'in' or 'out'")


def forecast(
    opening_balance_paise: int,
    entries: Iterable[ScheduledCash],
    *,
    start_date: date,
    days: int = 30,
) -> dict:
    """Project end-of-day cash; no receipt probability or ML claims.

    Entries due before start_date are excluded; collect past-due items separately
    and explicitly reschedule them rather than silently assuming payment today.
    """
    if not 1 <= days <= 365:
        raise ValueError("days must be between 1 and 365")
    events = {}
    for entry in entries:
        if start_date <= entry.due_date < start_date + timedelta(days=days):
            events[entry.due_date] = events.get(entry.due_date, 0) + (
                entry.amount_paise if entry.direction == "in" else -entry.amount_paise
            )
    balance = opening_balance_paise
    points = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        balance += events.get(day, 0)
        points.append({"date": day.isoformat(), "net_change_paise": events.get(day, 0), "balance_paise": balance})
    first_shortfall = next((point["date"] for point in points if point["balance_paise"] < 0), None)
    return {
        "currency": "INR",
        "method": "deterministic_scheduled_cashflows",
        "disclaimer": "Scenario projection, not a prediction of when invoices will be paid.",
        "opening_balance_paise": opening_balance_paise,
        "closing_balance_paise": balance,
        "first_shortfall_date": first_shortfall,
        "points": points,
    }


def receivables_aging(invoices: Iterable[tuple[date, int]], *, as_of: date) -> dict:
    """Group unpaid invoice balances (paise) by overdue age."""
    buckets = {"not_due": 0, "1_30": 0, "31_60": 0, "61_90": 0, "over_90": 0}
    for due_date, outstanding_paise in invoices:
        if outstanding_paise < 0:
            raise ValueError("outstanding invoice balance must not be negative")
        overdue = (as_of - due_date).days
        bucket = ("not_due" if overdue <= 0 else "1_30" if overdue <= 30
                  else "31_60" if overdue <= 60 else "61_90" if overdue <= 90 else "over_90")
        buckets[bucket] += outstanding_paise
    return buckets
