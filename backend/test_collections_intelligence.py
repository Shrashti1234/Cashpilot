from datetime import date
import pytest
from collections_intelligence import Receivable, collections_plan


def test_overdue_priority_and_dispute_resolution():
    result = collections_plan([
        Receivable("a", "Buyer A", date(2026, 10, 1), 500000),
        Receivable("b", "Buyer B", date(2026, 10, 15), 300000, disputed=True),
        Receivable("c", "Buyer C", date(2026, 11, 1), 100000),
    ], as_of=date(2026, 10, 23))
    assert result["total_outstanding_paise"] == 900000
    assert result["actions"][0]["action"] == "resolve_dispute"
    assert result["actions"][1]["action"] == "review_followup"
    assert result["actions"][2]["action"] == "monitor"


def test_recent_contact_cooldown():
    result = collections_plan([
        Receivable("a", "Buyer A", date(2026, 10, 1), 5000,
                   last_contacted=date(2026, 10, 22))
    ], as_of=date(2026, 10, 23))
    assert result["actions"][0]["action"] == "wait"


def test_zero_balance_excluded():
    result = collections_plan([Receivable("a", "A", date.today(), 0)], as_of=date.today())
    assert result["actions"] == []


def test_invalid_amount_rejected():
    with pytest.raises(ValueError):
        Receivable("a", "A", date.today(), -1)
