"""Explainable collections action planner for unpaid MSME invoices.

Pure business logic, no automated messaging or unsupported credit scoring.
Amounts are integer paise; predictions are never claimed as guaranteed.
"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Receivable:
    invoice_id: str
    customer_name: str
    due_date: date
    outstanding_paise: int
    disputed: bool = False
    last_contacted: date | None = None

    def __post_init__(self):
        if self.outstanding_paise < 0:
            raise ValueError("Outstanding amount must be non-negative")


def collections_plan(
    invoices: list[Receivable], *, as_of: date, max_actions: int = 10,
    contact_cooldown_days: int = 3
) -> dict:
    """Rank suggested human-reviewed actions; do not send messages automatically."""
    if not 1 <= max_actions <= 100:
        raise ValueError("max_actions must be between 1 and 100")
    if contact_cooldown_days < 0:
        raise ValueError("contact_cooldown_days must be nonnegative")
    actions = []
    total = 0
    for invoice in invoices:
        if invoice.outstanding_paise == 0:
            continue
        total += invoice.outstanding_paise
        overdue_days = max((as_of - invoice.due_date).days, 0)
        if invoice.disputed:
            action, reason, score = ("resolve_dispute", "Invoice marked disputed; resolve the issue before requesting payment", 100)
        elif invoice.last_contacted and 0 <= (as_of - invoice.last_contacted).days < contact_cooldown_days:
            action, reason, score = ("wait", "Customer contacted recently; avoid repeated reminders", 0)
        elif overdue_days > 0:
            action, reason = ("review_followup", f"Payment is {overdue_days} days overdue")
            score = min(overdue_days, 90) + min(invoice.outstanding_paise // 100000, 40)
        else:
            action, reason, score = ("monitor", "Invoice is not yet overdue", 0)
        actions.append({
            "invoice_id": invoice.invoice_id,
            "customer_name": invoice.customer_name,
            "outstanding_paise": invoice.outstanding_paise,
            "overdue_days": overdue_days,
            "action": action,
            "reason": reason,
            "priority_score": score,
        })
    actions.sort(key=lambda x: (-x["priority_score"], -x["outstanding_paise"], x["invoice_id"]))
    return {
        "as_of": as_of.isoformat(),
        "currency": "INR",
        "total_outstanding_paise": total,
        "method": "explainable_rules_not_ml",
        "disclaimer": "Recommendations require human review; no payment outcome is guaranteed.",
        "actions": actions[:max_actions],
    }
