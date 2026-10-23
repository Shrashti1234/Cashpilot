# CashPilot intelligence v1 — model card

**Training provenance: synthetic only. Experimental portfolio models; not validated for real-business financial decisions or credit underwriting.**

No third-party AI API is used for the core intelligence. Both served models were
trained locally with scikit-learn. The runtime evaluates exported JSON coefficients
with the Python standard library, without loading executable pickle artifacts.

## Payment lateness

Target: whether an invoice's final settlement happens after its due date. The
target is generated from a synthetic customer propensity and invoice amount.
Features are invoice amount, settled-history count, smoothed historic late share,
historic mean delay and days until due. Every historical settlement is filtered
strictly before the scoring date. No eventual payment date of an open invoice is
used as an input. Scores are not credit scores.

Generated dataset: 240 synthetic customers × 75 invoices. Purged temporal splits
retain 10,615 training rows, 2,889 validation/calibration rows and 3,999 test rows.
Training outcomes must resolve before 1 October 2024; calibration outcomes before
1 April 2025; test scores begin 1 April 2025. Rows crossing boundaries are excluded
from the earlier split. Customers recur across periods: this tests temporal
generalization, not performance on a held-out population of businesses.

Logistic regression C is selected from 0.05, 0.5 and 5 by validation Brier score.
A sigmoid calibrator is fitted on the separate validation period. A histogram
gradient-boosting model is evaluated as a comparator. The calibrated logistic
model is served for transparent additive explanations, with all comparator
results retained rather than reporting a model that is not deployed.

| Held-out synthetic model | ROC AUC | PR AUC | Brier | Log loss |
| --- | ---: | ---: | ---: | ---: |
| Base-rate baseline | 0.500 | 0.389 | 0.238 | 0.669 |
| Logistic, raw | 0.808 | 0.705 | 0.174 | 0.525 |
| Logistic, calibrated (served) | 0.808 | 0.705 | 0.175 | 0.524 |
| Gradient boosting comparator | 0.804 | 0.697 | 0.222 | 0.651 |

Late prevalence in the test set is 38.9%. Brier score and log loss are lower-is-better;
calibration does not improve every metric. The full calibration bins and unrounded
metrics are in [evaluation.json](../backend/models/evaluation.json).

Explanation contributions exactly reconstruct the calibrated log-odds, including
the intercept and calibration slope. These are model associations, not causal
effects or percentage-point changes. Exact linear contributions are used instead
of approximating them with SHAP. Already-overdue invoices are labelled as observed
facts, not assigned a new probability of becoming overdue. Unsupported feature
ranges and limited customer history are visible to the user.

## Operating expense forecasting

A ridge autoregression is trained on 32 synthetic daily expense series. Inputs
are lag 1, lag 7, trailing 7/28-day averages, weekday sine/cosine and month-end.
Amounts and targets are normalized by the trailing 28-day mean; scaling and
coefficients are fitted on training data only. The ridge penalty is selected on
later validation dates. Forecasts are recursive: future actual values are never
fed into future feature vectors during evaluation or serving.

Training uses days 28–649; validation/residual estimation uses 650–799; test
origins are 800, 910 and 1010. There are 96 test forecasts at each horizon.
The synthetic expense process contains weekly/month-end regularity, which makes
it easier than many real businesses. The model has not been validated on real
Indian MSMEs or on held-out business populations.

| Horizon | Ridge WAPE of horizon totals | Seasonal-naive WAPE |
| --- | ---: | ---: |
| 7 days | 4.37% | 6.82% |
| 30 days | 3.36% | 9.50% |
| 90 days | 3.50% | 10.41% |

WAPE is sum of absolute errors divided by sum of actual expenses. These metrics
are expense-total errors, not claimed accuracy of a business's closing cash.
Serving requires at least 56 calendar days with 28 recorded expense dates.
Short histories use a labelled trailing-mean fallback. With no expense history,
the UI says shortfall risk is not assessed. Missing calendar days are treated as
zero, so users must provide complete history.

## Decision Lab accounting and uncertainty

Opening cash is explicitly supplied by the user. The projection combines learned
operating expenses with outstanding invoice amounts and explicit non-invoice plans.
Recorded partial payments reduce invoice balances; they are not added again as
future income. Historical non-invoice income is not automatically extrapolated.

Planned outflows represent that day's total operating expenses, replacing its
model estimate. Rescheduling preserves the original amount and suppresses the
original scheduled day's model estimate. Obligations shifted beyond the displayed
horizon are explicitly reported as deferred, not saved.

300 Monte Carlo paths sample synthetic held-out expense residuals in seven-day
blocks and synthetic empirical invoice-delay samples conditional on modeled
lateness. Baseline, modified scenario and collection-review comparisons reuse the
same draws. Quantiles describe these assumptions; they are not real-world
calibrated coverage intervals or guaranteed shortfall probabilities. Invoice
timings are sampled independently, macroeconomic shocks/default are not modeled,
and old overdue invoices can exceed the synthetic delay support. Open disputes
are excluded from baseline receipts. Explicit receipt dates assume the outcome
is achieved; no causal claim about collection actions is made.

No simulation changes ledger records, records payments, contacts customers,
reschedules actual expenses or executes financial decisions. Demo mode constructs
labelled synthetic inputs in memory and never writes fake business records.

## Reproduction and artifact integrity

From the repository root, install the backend requirements and
`backend/training/requirements.txt` in an isolated environment, then run:

```text
cd backend
python training/train.py
python -m pytest -q
```

Seed: 20261023. Training versions and the exported artifact SHA-256 are recorded in
evaluation.json. The checked-in artifact's checksum is tested in CI, and the
training pipeline checks its JSON predictions against scikit-learn predictions.
Numerical differences across platforms/BLAS versions may change the exact hash
on retraining; evaluate and version any regenerated artifact deliberately.

Before real-business use: obtain appropriately licensed, consented representative
data, validate forward in time and on held-out businesses, audit missingness and
calibration, evaluate interval coverage and economic cost, and review with domain
experts. Synthetic benchmark results are not a substitute for that work.
