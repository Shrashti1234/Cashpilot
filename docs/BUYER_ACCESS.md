# Local buyer access and payment commitments

Implemented locally; no deployment or remote migration performed.

Owners/admins create invoice-specific links valid for 1–30 days and select whether
the holder can raise an issue or record a payment promise. The random 256-bit secret
is returned once, stored only as a SHA-256 digest, and sent to the buyer API in a
POST body. The public route removes its initial URL fragment and does not save the
secret to browser storage. Anyone holding the link has the selected capability;
this does not verify the buyer's identity. Share through a trusted channel.

The public view contains only the selected invoice, supplier details, recipient
name, balances, public issue status and commitment summaries. Internal notes,
membership details, other invoices, audit history and model scores are excluded.
Responses disable caching. Expired or revoked access is refused; revocation is
checked on each request and the Refresh control clears unavailable invoice data.
Already viewed information cannot be recalled from a recipient.

Commitments are separate from receipts. Amounts are integer paise, capped at the
current unpaid balance; dates are today through 90 days ahead. One unfulfilled
commitment per invoice is permitted. Replay keys prevent duplicate creation.
Recorded receipts since the commitment determine fulfilment. Credit memos do not
count as received cash. Businesses can cancel an unfulfilled commitment with a
reason. Staff-created and private-link submissions have distinct provenance.
Collection plans show commitment context without manufacturing received money.

New buyer issues enter the existing dispute workflow. A link cannot overwrite an
existing issue or resolve it. Payment collection remains unavailable until a real
provider is configured and its sandbox flow passes verification.

## Verification

- 90 backend tests pass, including seven actual local PostgreSQL checks, migration
  parity, restricted runtime grants and backup restoration.
- 46 frontend tests pass; production build passes.
- Local Edge browser: owner creates a masked private link; buyer sees the selected
  invoice, records an exact-paise commitment, raises an issue; owner cancels the
  commitment; revoked access clears the invoice on refresh. No page errors.
- Mobile buyer view checked at 390 pixels wide with no page overflow.
- Local fixture authentication lives outside the repository. It does not replace
  or validate the production Supabase JWT flow. Nothing was sent to a customer.

Remaining related work: provider payments, delivery/consent/reminders, attachments,
buyer identity verification where required, public-route hosting/access policy,
localization, and deployment acceptance.
