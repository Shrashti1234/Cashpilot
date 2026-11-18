# Local forecast journal and actual-expense reviews

Implemented locally; no scheduler, notification provider or deployment enabled.

Writable members can save today's immutable 7/30/90-day expense outlook. Snapshots
retain the served model version and artifact hash, input digest, expense method,
history coverage, dated projections and warnings. Replay keys prevent duplicates.
The public API cannot backdate a forecast. Insufficient recent history uses an
explicit fallback; expense dates older than the one-year window no longer count
toward learned-model eligibility.

Optionally, users supply opening cash and an attention threshold for a saved
90-day conditional simulation. An in-app attention flag identifies the first
simulated median curve point below the chosen threshold. Synthetic-path shortfall
frequency is labelled conditional and unvalidated, and no bank balance is inferred.
The immutable snapshot does not initiate collection, record money or send alerts.

After each complete forecast window ends, the detail screen compares its saved
expense total with current recorded actual operating expenses. Invoice receipts,
planned/void entries and completed refunds are excluded. Open windows show no
actual total. Closed comparisons remain provisional until a writer explicitly
reviews and confirms complete operating-expense records for the period.

Reviews store a digest of actual entry IDs, dates and amounts. Later amount/date/
direction/status changes or added/removed actual entries invalidate the review.
Percentage error is shown only for a current confirmed review with nonzero actual
spending. Empty records do not establish zero spending, and a completeness review
is a user's statement, not independent reconciliation. This journal does not turn
synthetic benchmark accuracy into validated performance on real businesses.

PostgreSQL runtime access to snapshots and reviews is SELECT/INSERT only; neither
can be updated/deleted. All API access is tenant-scoped, viewers cannot save or
confirm, and financial values retain integer paise with display-precision checks.
Snapshot JSON exports contain projections and comparisons, not raw input rows.

`forecast_jobs.py` is an explicit job entrypoint for expense-only snapshots, with
an active writable member and stable occurrence replay key. It does not install a
scheduler or infer fresh opening cash. A future scheduler requires separate setup.

Verified: 110 backend tests including ten actual PostgreSQL checks, 55 frontend
tests and production build. Local Edge: save today's conditional forecast → open
comparison windows; historical synthetic fixture → completeness review → edit an
expense → stale review detected. Mobile width 390 had no page overflow or page
errors. Historical fixture insertion and test authentication are outside the app.

Remaining scope: installed scheduling, provider notifications, real-world model
validation, statistical drift analysis, seasonality diagnostics and bank-verified
opening-cash integration. In-app conditional attention is not automatic delivery.
