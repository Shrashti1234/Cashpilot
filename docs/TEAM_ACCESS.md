# Team access — local build

Local schema: `0009_team_access`. This is not deployed; hosted memberships and
authentication settings have not been changed.

Owners/admins open **Team & access**. A recipient signs in and copies **Your
account code** from Your businesses. The administrator creates a private invitation
for that exact account and role, then shares its code directly. The recipient
pastes it into **Join an invited business**.

Invitation codes have 256 bits of random input, expire in seven days and are
stored only as SHA-256 hashes. The raw code is returned once and remains only in
component memory until hidden or the screen closes. It is not put into a URL,
audit payload, list response or browser storage. No message is sent automatically.

Acceptance requires the authenticated subject to match the intended account.
Expired/revoked codes fail. Current inviter permissions are checked again at
acceptance; an old invitation cannot overwrite a newer active membership or
restore access after its already-used invitation is revoked through membership
deactivation. An administrator cannot invite or manage owners/administrators.

Owners can manage roles, add another owner, and deactivate/reactivate membership.
The last active owner cannot be demoted/deactivated. Business-level locks serialize
team mutations. Membership authorization is read from the database on every
protected route: deactivated users lose future API access even while their Auth
token still verifies. Other business memberships remain independent.

Role grants/revocation and invitation lifecycle events are audited. Role changes
to one's own account return the UI to workspace selection so its permissions are
reloaded. Invite acceptance has an instance-local attempt limit; distributed
limits remain part of the unfinished enterprise work.

## Verification

Tests cover token hashing, subject binding, replay, expiry, revocation, inviter
demotion, last-owner protection, privilege escalation, cross-tenant denial and
already-signed-in identity access after deactivation. Frontend checks cover masked
private codes, role controls, join flow and clearing selected business access.

The local browser used two explicit fixture identities outside the application
repository. It created an admin invitation, accepted it with the intended account,
approved an owner's draft as the different administrator, issued the approved
invoice, and deactivated the administrator. Their next business API read returned
403. Desktop/mobile layouts had no page errors or horizontal page overflow. The
run exercised real application/database code with local test identities, not
hosted JWT authentication or actual email delivery.

Current validation: **78 backend tests, 39 frontend tests and TypeScript/Vite
build pass**. Branch scoping, custom permission sets, finance-adjustment approvals,
email invitation delivery and broader enterprise controls remain unfinished.
