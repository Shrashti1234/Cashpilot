# Local statement reconciliation

Implemented locally with manually supplied INR CSV files. No live bank connection,
account verification, receipt creation or cloud deployment is implied.

Owners/admins create an account alias; no credentials or full account numbers are
required. Writers preview and import up to 1,000 rows / 1 MB per file using exactly:

```csv
booked_date,reference,description,amount_inr,currency
```

Dates are ISO booking dates from 2000 through today in India. Amounts use signed
INR with at most two decimal places and no thousands separators; credits are
positive and debits negative. A stable bank transaction reference is mandatory.
Repeated identical references in an account are skipped. Changed details for an
existing reference, duplicate references within a file, malformed rows, non-INR
currencies and ambiguous amounts reject the whole import. Preview saves nothing.

Statement rows can be matched to existing invoice receipts, completed external
refund records or actual cash entries. Amount and direction must match exactly.
The operator selects a candidate, records a note and explicitly confirms that
references and dates identify the same transaction. Candidate amounts alone are
not evidence of identity. At most one active match per statement row and ledger
record is enforced by partial unique indexes. Reversal requires a reason and
preserves match history. Matched cash entries cannot be edited until reversal.

These imports never change receivables, create payments or manufacture cash.
Imported net change is labelled separately from a bank balance. The screen shows
the latest 1,000 rows while totals cover the entire imported account. CSV exports
neutralize formula-like text. Viewers can inspect records without write controls.

PostgreSQL runtime grants permit inserting and reading statement evidence, with
no UPDATE/DELETE access. Business control locks serialize imports and competing
matches. Composite tenant foreign keys and unique indexes protect target links.

Verified with backend permission, replay, atomicity, direction, edit-lock and
real PostgreSQL concurrency checks. Local Edge browser passed preview → import →
select existing receipt → match → reverse; mobile width 390 had no page overflow
and no page errors. The browser fixture is external to the production application.

Remaining scope: live provider ingestion and sandbox validation, statement format
mappings, split/fee settlements, transfer matching, reconciliation closing,
opening/closing balance validation, large-account pagination and independent
reconciliation approvals. This is a usable local manual workflow, not completion
of the complete bank-integration roadmap.
