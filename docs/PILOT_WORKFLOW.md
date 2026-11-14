# Pilot workflow

1. Export the bill-wise receivables report from TallyPrime and save a flat sheet as
   UTF-8 CSV, or export a CSV from Excel. See the [TallyPrime receivables guide](https://help.tallysolutions.com/manage-receivables-outstanding-tally/).
2. An owner/admin opens **Import open invoices**, chooses the file and maps customer
   name, unique bill reference, due date and **pending INR amount**. Remove subtotals,
   party-only balances and foreign-currency rows. Keep leading zeros in references.
3. Review the preview and download any row errors. Correct the file before confirming.
   The limit is 500 rows, 500,000 characters and 1 MB per file. Dates accept ISO or
   DD/MM/YYYY. Imports reuse unambiguous exact customer names and create missing
   customers. The invoice reference must be unique across the workspace.
4. Import posts opening receivables atomically. It creates no sale, GST document or
   payment. Exact replays skip already imported records; a changed pending amount is
   a conflict, not an overwrite. Workspaces requiring invoice approval cannot use this
   import yet. Opening receivables stay outside issued-invoice totals and historical
   payment-timing training inputs.
5. Open **Collections worklist** to search and page through open balances. Owners and admins
   can assign work; accountants can claim unassigned items and update their own.
   The list shows existing dispute, promise and contact-cooldown guidance and filters
   for owned, due or unassigned items across the workspace. Follow-ups due now are
   shown first, followed by invoice due date. It sends no message.

## Run a provider-free walkthrough

For a browser walkthrough with no account or credentials, install the normal
backend and frontend dependencies, then start the two loopback servers:

- From `backend`: `python pilot_demo.py`
- From `frontend`: `npm exec -- vite --host 127.0.0.1 --port 5179 --strictPort`

Open [the local practice screen](http://127.0.0.1:5179/practice.html). It uses
a temporary local database, independent of the hosted API and database. A normal
API shutdown discards the practice data; each start creates a fresh workspace.
The page offers both sample downloads and the
four workspace screens. If using a separate authenticated practice workspace
instead, use the two [sample CSV files](../examples/pilot). They are synthetic;
do not import them into a workspace with real balances.

1. Import `open-receivables.csv`. Search for `PILOT-100` in **Collections worklist**
   and assign a follow-up.
2. Go to **Invoices & receipts**, open **Payments** on `PILOT-100`, and record
   the sample receipt of ₹1,000. The settled invoice leaves the open worklist.
3. In **Bank statement reconciliation**, create an account alias, import
   `bank-statement.csv`, and open `PILOT-BANK-1`. Review the sample amount and
   reference, select **Receipt · PILOT-100 · Pilot Buyer**, and confirm the
   match. Reconciliation links the existing receipt without creating another.
   The sample bank booking date and the receipt's CashPilot recording date
   are separate facts.

To run the same scenario without any account or secrets, install the backend
requirements and run `python -m pytest test_pilot_workflow.py -q` from `backend`.
The test uses an isolated database and covers duplicate receipt requests.

Native Tally/XLSX parsing, Tally writeback, automated messages, and online
checkout remain out of this checkpoint. A provider sandbox is only needed
for the online payment and settlement acceptance gate.
