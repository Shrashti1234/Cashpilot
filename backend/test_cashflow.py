from datetime import date
import pytest

from cashflow import ScheduledCash, forecast, receivables_aging


def test_forecast_inflows_outflows_and_shortfall():
    result = forecast(
        10000,
        [
            ScheduledCash(date(2026, 11, 1), 20000, "out", "Rent"),
            ScheduledCash(date(2026, 11, 2), 25000, "in", "Invoice"),
        ],
        start_date=date(2026, 11, 1),
        days=3,
    )
    assert result["first_shortfall_date"] == "2026-11-01"
    assert result["closing_balance_paise"] == 15000
    assert [p["balance_paise"] for p in result["points"]] == [-10000, 15000, 15000]


def test_past_due_not_assumed_paid():
    result = forecast(100, [ScheduledCash(date(2026, 10, 1), 500, "in")],
                      start_date=date(2026, 10, 23), days=2)
    assert result["closing_balance_paise"] == 100


def test_aging_buckets():
    result = receivables_aging([
        (date(2026, 10, 24), 100),
        (date(2026, 10, 22), 200),
        (date(2026, 9, 1), 300),
        (date(2026, 7, 1), 400),
    ], as_of=date(2026, 10, 23))
    assert result == {"not_due": 100, "1_30": 200, "31_60": 300, "61_90": 0, "over_90": 400}


def test_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        ScheduledCash(date.today(), -1, "in")
    with pytest.raises(ValueError):
        ScheduledCash(date.today(), 1, "unknown")
    with pytest.raises(ValueError):
        forecast(0, [], start_date=date.today(), days=0)
    with pytest.raises(ValueError):
        receivables_aging([(date.today(), -1)], as_of=date.today())
