# External invoice late-payment benchmark

The [Customer Invoices Dataset v1](https://www.kaggle.com/datasets/pradumn203/payment-date-prediction-for-invoices-dataset) was published by Pradumn Mishra on Kaggle under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). This offline evaluation uses the public dataset for noncommercial benchmarking. The dataset card does not establish the businesses' origin or verify whether the records represent observed transactions. Raw records are downloaded separately.

## Method

The CSV has 50,000 rows. Cleaning removed 1,161 duplicate documents and 6 non-invoice documents. Of the remaining rows, 9,681 lack a clearing date and 104 were overdue or had cleared before the posting date. The target is whether clearing occurred after the invoice due date. Clearing date is the dataset's payment proxy. The benchmark assumes the reported amount was available at posting, maps USD and CAD to rupees using fixed 2017 annual averages from [FRED AEXINUS](https://fred.stlouisfed.org/data/AEXINUS) and [FRED AEXCAUS](https://fred.stlouisfed.org/data/AEXCAUS), and uses CashPilot's shared feature function. Customer history uses only invoices cleared strictly before the invoice being scored was posted.

| Split | Invoice rows | Posting window |
| --- | ---: | --- |
| Training | 24,634 | Before 1 October 2019 |
| Calibration | 4,261 | 1 October–30 November 2019 |
| Test | 6,748 | 1 December 2019–29 February 2020 |

Training and calibration outcomes had to clear before the next split began. The test contains 549 customers, with 91 invoices from customers absent in training. The test metrics cover invoices with observed clearing dates. Another 348 eligible invoices in the test window lack a clearing date and have no measured outcome.

## Test results

| Model | ROC AUC ↑ | Average precision ↑ | Brier score ↓ |
| --- | ---: | ---: | ---: |
| Constant training late rate | 0.5000 | 0.3896 | 0.2386 |
| Customer's smoothed past late rate | 0.7748 | 0.7181 | 0.1803 |
| Existing CashPilot model | 0.7485 | 0.6936 | 0.2203 |
| New calibrated logistic model | 0.7820 | 0.7233 | 0.1794 |

The new model improved ranking and probability error over the existing model. Its improvement over the customer-history baseline was small. On 6,217 test invoices, at least one feature fell outside the existing model's synthetic training range. This benchmark measures invoice lateness at posting in one dataset. It leaves performance on Indian MSMEs, unpaid invoices and operating expense forecasting untested. The [candidate coefficients](payment-candidate.json) are an offline research artifact. The application continues to load its existing model.

## Reproduce

Run from the repository root with Python 3.11 or newer and the pinned training dependencies installed.

```text
python -m pip install -r backend/training/requirements.txt
python backend/training/benchmark_invoices.py <downloaded-kaggle-zip> <output-directory>
```

The script checks the downloaded CSV's SHA-256, verifies exported coefficient predictions against scikit-learn, and emits the model and [full evaluation](evaluation.json).
