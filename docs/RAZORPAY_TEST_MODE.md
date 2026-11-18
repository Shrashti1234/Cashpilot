# Razorpay Test Mode

CashPilot supports a full-balance INR test checkout from a private buyer link. The buyer pays on Razorpay's hosted page. A signed `payment_link.paid` webhook records one test receipt against the original invoice. A refresh on the buyer page shows the resulting balance.

## Set up a test workspace

1. Use a dedicated CashPilot workspace with sample invoices and a Razorpay account in **Test Mode**. Apply the repository's Alembic migrations to the test database before starting the SaaS API.
2. Set the following server environment variables. Keep secrets in the API environment.

   | Variable | Value |
   | --- | --- |
   | `RAZORPAY_TEST_ORGANIZATION_ID` | ID of the CashPilot workspace that holds test invoices |
   | `RAZORPAY_TEST_ACCOUNT_ID` | Razorpay merchant account ID beginning with `acc_` |
   | `RAZORPAY_TEST_KEY_ID` | Razorpay Test Mode API key ID beginning with `rzp_test_` |
   | `RAZORPAY_TEST_KEY_SECRET` | Secret paired with the test API key |
   | `RAZORPAY_TEST_WEBHOOK_SECRET` | Secret shared with the Razorpay Test Mode webhook |

3. In Razorpay Test Mode, subscribe to `payment_link.paid` at the HTTPS URL for your test API, ending in `/api/v1/webhooks/razorpay/test`. Configure the same webhook secret on both sides. Razorpay delivery requires a publicly reachable test URL. [Razorpay webhook setup and testing](https://razorpay.com/docs/webhooks/validate-test)
4. In CashPilot, open **Buyer access & commitments**, choose a sample invoice with at least ₹1 outstanding, select **Allow Razorpay test checkout**, and create the private link. Open that link, prepare the test payment, then open Razorpay checkout in the new tab. After completing the test transaction, return and select **Refresh invoice**.

The payment link expires within 30 minutes or at the buyer link's expiry, whichever comes first. Revoking buyer access stops new checkout requests from that link. A Razorpay checkout already issued remains usable until its provider expiry. If a separate receipt reduces the balance after checkout was issued, the captured test receipt is recorded and any overpayment appears as customer credit. Partial checkout, real-money payments, provider refunds, and settlement reconciliation are outside this integration.

The local test suite exercises Razorpay-shaped responses and signed confirmations with no external account. Run `python -m pytest test_buyer_api.py -k razorpay` from the `backend` directory to verify permissions, checkout recovery, and duplicate confirmation handling.
