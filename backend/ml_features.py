"""Shared, dependency-free feature definitions for training and serving."""
import math
from datetime import date

PAYMENT_FEATURES = ["log_invoice_rupees", "prior_paid_count", "prior_late_rate", "prior_mean_delay_days", "days_until_due"]
FLOW_FEATURES = ["lag_1", "lag_7", "mean_7", "mean_28", "weekday_sin", "weekday_cos", "month_end"]


def payment_features(amount_paise: int, due: date, as_of: date, settled_history: list[dict]) -> list[float]:
    # Strict as-of filtering: the outcome of an unsettled/future invoice is never a feature.
    history = [h for h in settled_history if h["paid_date"] < as_of]
    delays = [(h["paid_date"] - h["due_date"]).days for h in history]
    return [math.log1p(amount_paise / 100), min(len(delays), 100),
            (sum(d > 0 for d in delays) + 2) / (len(delays) + 5),
            sum(max(-14, min(d, 90)) for d in delays) / max(len(delays), 1),
            max(0, min((due - as_of).days, 90))]


def flow_features(history: list[float], day: date) -> list[float]:
    if len(history) < 28:
        raise ValueError("At least 28 calendar days of history are required")
    return [history[-1], history[-7], sum(history[-7:]) / 7, sum(history[-28:]) / 28,
            math.sin(2 * math.pi * day.weekday() / 7), math.cos(2 * math.pi * day.weekday() / 7),
            float(day.day >= 26)]


def linear_predict(model: dict, values: list[float]) -> float:
    return model["intercept"] + sum(c * (x - mean) / scale for c, x, mean, scale in
                                  zip(model["coefficients"], values, model["means"], model["scales"], strict=True))


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-max(-40, min(40, value))))
