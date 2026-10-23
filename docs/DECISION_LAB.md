# Decision Lab user guide

Open a business workspace, then **Decision Lab**. The initial view is an explicitly
labelled synthetic demo. Switching to **Use my business data** reads only records
in the selected workspace.

1. Enter current available cash as an opening-balance assumption.
2. Choose a 7-, 30- or 90-day horizon.
3. Choose an invoice and an assumed full-receipt date, a planned expense and its
   assumed new date, or both. Click **Compare scenario**.
4. Compare median cash paths, the conditional 10–90% baseline band, minimum-cash
   impact and shortfall frequencies. Deferrals beyond the horizon are labelled.
5. Review collection assumptions and invoice-level feature contributions. Nothing
   is executed; changing a scenario never records an invoice payment.

**Cash history** supports actual expenses, planned day-total expenses, explicit
non-invoice income and voided/excluded records. Entries can be corrected without
deleting their audit history. Do not enter an invoice receipt again as other
income. Supply complete daily expense history: missing dates count as zero.

CSV imports are transactional and accept at most 1,000 rows / 300 KB. Exact header:

```csv
date,direction,status,amount_inr,description
2026-10-01,out,actual,1250.50,Office expense
```

Direction is `in` or `out`; status is `actual`, `planned` or `void`. Amounts must
be positive and have at most two decimal places. Actual entries cannot be future
dated. All rows are appended; importing the same file again duplicates its rows.
Review before submitting. Viewers can simulate and inspect, but cannot write.

**Model evidence** reports the actual trained models, baseline comparisons,
held-out synthetic metrics and artifact fingerprint. Read [the model card](MODEL_CARD.md)
for dataset generation, leakage controls, evaluation and limitations.

**Disputes & activity**, on the customer workspace screen, supports an invoice's
open → under review → resolved workflow. Resolving requires a note. An open
dispute is excluded from baseline Decision Lab receipts. The activity view shows
the latest 100 tenant-scoped audit events; runtime credentials cannot modify or
delete that audit trail.

This is an experimental decision-support tool. Scores are not credit scores,
scenario frequencies are not validated real-world probabilities, and no action's
outcome is guaranteed.
