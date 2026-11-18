"""Train an offline payment model on the Kaggle Customer Invoices benchmark."""
import argparse
import csv
import hashlib
import io
import json
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zipfile import ZipFile

from train import (
    PAYMENT_FEATURES, ROOT, SEED, classifier_metrics, export_linear, linear_predict,
    payment_features, sigmoid,
)
import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


SOURCE = "https://www.kaggle.com/datasets/pradumn203/payment-date-prediction-for-invoices-dataset"
CSV_SHA256 = "3409441a8ecc48438a0fd42421ce3230d95305f7afcefb732bf232a948b6cf88"
TRAIN_END = date(2019, 10, 1)
TEST_START = date(2019, 12, 1)
TEST_END = date(2020, 3, 1)
# Fixed pre-sample annual averages from FRED AEXINUS and AEXCAUS (2017).
RUPEES = {"USD": Decimal("65.0659"), "CAD": Decimal("65.0659") / Decimal("1.2984")}


def read_invoices(archive):
    with ZipFile(archive) as source:
        raw = source.read("dataset.csv")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != CSV_SHA256:
        raise ValueError(f"Unexpected dataset.csv SHA-256: {digest}")

    counts = Counter()
    seen = set()
    invoices = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        counts["raw_rows"] += 1
        if row["document type"] != "RV":
            counts["non_invoice"] += 1
            continue
        key = (row["business_code"], row["doc_id"])
        if key in seen:
            counts["duplicates"] += 1
            continue
        seen.add(key)
        try:
            scored = date.fromisoformat(row["posting_date"])
            due = date.fromisoformat(row["due_in_date"].split(".")[0])
            paid = date.fromisoformat(row["clear_date"][:10]) if row["clear_date"] else None
            customer = row["cust_number"].strip().lstrip("0")
            amount = Decimal(row["total_open_amount"]) * RUPEES[row["invoice_currency"]]
            if not customer or not row["doc_id"] or not amount.is_finite() or amount <= 0:
                raise ValueError("Invalid invoice")
            paise = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (ValueError, InvalidOperation, KeyError):
            counts["invalid"] += 1
            continue
        invoices.append((customer, scored, due, paid, paise))
    return invoices, counts


def build_splits(invoices, counts):
    histories = defaultdict(list)
    for customer, _, due, paid, _ in invoices:
        if paid is not None:
            histories[customer].append({"due_date": due, "paid_date": paid})
    for history in histories.values():
        history.sort(key=lambda invoice: invoice["paid_date"])
    paid_dates = {customer: [invoice["paid_date"] for invoice in history]
                  for customer, history in histories.items()}
    splits = {"train": [], "calibration": [], "test": []}
    for customer, scored, due, paid, paise in invoices:
        if paid is None:
            counts["unlabelled"] += 1
            if TEST_START <= scored < TEST_END and due >= scored:
                counts["unlabelled_test_window"] += 1
            continue
        if due < scored or paid < scored:
            counts["already_overdue_or_settled_at_posting"] += 1
            continue
        if scored < TRAIN_END and paid < TRAIN_END:
            split = "train"
        elif TRAIN_END <= scored < TEST_START and paid < TEST_START:
            split = "calibration"
        elif TEST_START <= scored < TEST_END:
            split = "test"
        else:
            counts["outside_split_or_purged"] += 1
            continue
        cutoff = bisect_left(paid_dates[customer], scored)
        values = payment_features(paise, due, scored, histories[customer][:cutoff])
        delay = (paid - due).days
        splits[split].append((customer, scored, values, delay))
    return splits


def features_and_labels(rows):
    return np.array([row[2] for row in rows]), np.array([int(row[3] > 0) for row in rows])


def probabilities(artifact, features):
    return np.array([sigmoid(artifact["calibration_intercept"] + artifact["calibration_slope"]
                            * linear_predict(artifact, row)) for row in features])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Original Kaggle ZIP download")
    parser.add_argument("output", type=Path, help="Directory for the offline model and report")
    args = parser.parse_args()
    invoices, counts = read_invoices(args.archive)
    splits = build_splits(invoices, counts)
    xt, yt = features_and_labels(splits["train"])
    xv, yv = features_and_labels(splits["calibration"])
    xe, ye = features_and_labels(splits["test"])

    model = make_pipeline(StandardScaler(), LogisticRegression(C=1, max_iter=1000, random_state=SEED))
    model.fit(xt, yt)
    calibrator = LogisticRegression(C=1e6, max_iter=1000)
    calibrator.fit(model.decision_function(xv).reshape(-1, 1), yv)
    artifact = export_linear(model)
    artifact.update({
        "features": PAYMENT_FEATURES,
        "calibration_slope": float(calibrator.coef_[0, 0]),
        "calibration_intercept": float(calibrator.intercept_[0]),
        "training_support": {"min": xt.min(axis=0).tolist(), "max": xt.max(axis=0).tolist()},
        "source_csv_sha256": CSV_SHA256,
    })
    candidate = probabilities(artifact, xe)
    expected = calibrator.predict_proba(model.decision_function(xe).reshape(-1, 1))[:, 1]
    np.testing.assert_allclose(candidate, expected, atol=1e-10, rtol=0)

    served_bytes = (ROOT / "models" / "intelligence.json").read_bytes()
    served = json.loads(served_bytes)["payment"]
    predictions = {
        "training_prevalence": np.full(len(ye), yt.mean()),
        "customer_history": xe[:, PAYMENT_FEATURES.index("prior_late_rate")],
        "existing_cashpilot": probabilities(served, xe),
        "new_candidate": candidate,
    }
    out_of_range = (xe < served["training_support"]["min"]) | (xe > served["training_support"]["max"])
    train_customers = {row[0] for row in splits["train"]}
    report = {
        "source": SOURCE,
        "source_csv_sha256": CSV_SHA256,
        "existing_bundle_sha256": hashlib.sha256(served_bytes).hexdigest(),
        "sklearn_version": sklearn.__version__,
        "counts": dict(counts),
        "splits": {
            name: {"rows": len(rows), "customers": len({row[0] for row in rows}),
                   "first_posting": str(min(row[1] for row in rows)),
                   "last_posting": str(max(row[1] for row in rows))}
            for name, rows in splits.items()
        },
        "test_rows_from_customers_absent_in_training": sum(row[0] not in train_customers for row in splits["test"]),
        "outside_existing_model_support": {
            "any_feature": int(out_of_range.any(axis=1).sum()),
            **dict(zip(PAYMENT_FEATURES, out_of_range.sum(axis=0).tolist(), strict=True)),
        },
        "metrics": {name: classifier_metrics(ye, predicted) for name, predicted in predictions.items()},
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, data in (("payment-candidate.json", artifact), ("evaluation.json", report)):
        (args.output / filename).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
