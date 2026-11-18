# Local private invoice record export

Owners/admins can preview and explicitly download one invoice's combined private
records. No other person receives a message or file automatically.

The ZIP contains the current invoice/customer/profile, immutable issued source
documents when available, adjusted ledger with receipts/memos/refunds, issues,
payment commitments, that invoice's completed contact records, the customer's
consent evidence history, related bank-match/reversal evidence, related audit
activity, and a readable scope note. Missing originals and issue dates are not
invented. Internal financial notes are intentionally included for the authorized
business reviewer; other invoices' contact notes and other tenants are excluded.

Buyer-link codes and their hashes, authentication credentials and replay keys are
excluded. Manually imported statement rows and business-recorded contacts are not
independently verified provider evidence. Uploaded source files are not yet part
of this feature. Internal memos are not certified statutory GST notes.

`manifest.json` records SHA-256 and byte size for ten files, including financial
approval requests and decisions. The verifier checks
the complete file list and limits archive sizes without extracting files. These
checks detect changed files against the supplied manifest; they do not establish
authenticity, third-party certification or a trusted timestamp. An attacker able to
replace both records and manifest can generate another consistent manifest.

```powershell
python backend/verify_evidence.py path/to/cashpilot-invoice-records.zip
```

The bundle is limited to 2,000 entries per record category and 16 MB uncompressed.
Exceeding a limit rejects the export rather than silently omitting records. The
preview is informational; download reads current records again. Every completed
export is audited. No cloud deployment or remote migration was performed.

Verification: 119 backend tests including twelve real PostgreSQL checks, 61
frontend tests and production build pass. Tests cover role/tenant boundaries,
exclusion of private capability codes/hashes, all manifest checksums, restricted
runtime permissions and rejection of modified ZIP contents. Local Edge downloaded
a real fixture ZIP; the standalone verifier checked the bundle files. Mobile width
390 had no page overflow and no page errors.

Remaining: private original-document storage and scanning, provider-sourced
delivery/settlement evidence, broader organization exports, configurable retention
and reviewed regulatory workflows. This export is an application record bundle.
