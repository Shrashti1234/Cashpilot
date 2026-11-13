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

This checkpoint does not parse native Tally or XLSX files, write vouchers back to
Tally, or connect a payment or messaging provider. Next pilot acceptance gate:
one real provider sandbox payment matched to the correct invoice and settlement,
including duplicate event and refund cases. Then validate the workflow against
representative pilot exports before any hosted release.
