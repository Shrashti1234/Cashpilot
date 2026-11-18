"""Razorpay Test Mode checkout for one explicitly selected practice business."""
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import BigInteger, CheckConstraint, ForeignKeyConstraint, Index, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from audit import record_event
from disputes import InvoiceDispute
from operations_api import mutation
from saas_api import Db
from saas_domain import RAZORPAY_TEST_PAYMENT_PREFIX, Invoice, Payment, SaaSBase, invoice_positions, new_id

router = APIRouter(prefix='/api/v1/webhooks', tags=['payments'])
LINK_DURATION = 30 * 60


class RazorpayCheckout(SaaSBase):
    __tablename__ = 'saas_razorpay_checkouts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(String(36))
    invoice_id: Mapped[str] = mapped_column(String(36))
    account_id: Mapped[str] = mapped_column(String(80))
    amount_paise: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(BigInteger)
    provider_link_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    checkout_url: Mapped[str | None] = mapped_column(String(512))
    provider_payment_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    __table_args__ = (
        ForeignKeyConstraint(['organization_id', 'invoice_id'], ['saas_invoices.organization_id', 'saas_invoices.id']),
        CheckConstraint('amount_paise BETWEEN 100 AND 2000000000'),
        Index('ix_razorpay_checkout_invoice_expiry', 'organization_id', 'invoice_id', 'expires_at'),
    )


@dataclass(frozen=True)
class TestSettings:
    organization_id: str
    account_id: str
    key_id: str
    key_secret: str
    webhook_secret: str


def test_settings():
    organization_id, account_id, key_id, key_secret, secret = (
        os.getenv(name, '').strip() for name in (
            'RAZORPAY_TEST_ORGANIZATION_ID', 'RAZORPAY_TEST_ACCOUNT_ID', 'RAZORPAY_TEST_KEY_ID',
            'RAZORPAY_TEST_KEY_SECRET', 'RAZORPAY_TEST_WEBHOOK_SECRET',
        )
    )
    if organization_id and valid_id(account_id, 'acc') and valid_id(key_id, 'rzp_test') and key_secret and secret:
        return TestSettings(organization_id, account_id, key_id, key_secret, secret)
    return None


def valid_id(value, prefix):
    return isinstance(value, str) and len(value) <= 80 and re.fullmatch(prefix + r'_[A-Za-z0-9]+', value)


def test_payment_available(organization_id, balance, dispute, expires_at):
    settings = test_settings()
    return bool(settings and settings.organization_id == organization_id
                and 100 <= balance <= 2_000_000_000 and (not dispute or dispute.status == 'resolved')
                and expires_at.timestamp() - datetime.now(timezone.utc).timestamp() > 16 * 60)


def request_razorpay(settings, method, **kwargs):
    try:
        response = httpx.request(method, 'https://api.razorpay.com/v1/payment_links',
                                 auth=(settings.key_id, settings.key_secret), timeout=8, **kwargs)
        response.raise_for_status()
        result = response.json()
        if isinstance(result, dict):
            return result
    except (httpx.HTTPError, ValueError):
        pass
    raise HTTPException(502, 'Razorpay checkout is temporarily unavailable. Try again.')


def provider_link(settings, checkout, invoice_number):
    found = request_razorpay(settings, 'GET', params={'reference_id': checkout.id}).get('payment_links')
    if not isinstance(found, list) or any(not isinstance(row, dict) for row in found):
        raise HTTPException(502, 'Razorpay checkout could not be verified.')
    matches = [row for row in found if row.get('reference_id') == checkout.id]
    if len(matches) > 1:
        raise HTTPException(502, 'Razorpay checkout could not be verified.')
    if matches:
        return matches[0]
    return request_razorpay(settings, 'POST', json={
        'reference_id': checkout.id, 'amount': checkout.amount_paise, 'currency': 'INR',
        'description': f'CashPilot test payment for {invoice_number}',
        'expire_by': checkout.expires_at, 'accept_partial': False,
        'notify': {'email': False, 'sms': False}, 'reminder_enable': False,
    })


def locked_invoice(db, organization_id, invoice_id):
    return db.scalar(select(Invoice).where(Invoice.organization_id == organization_id,
                                           Invoice.id == invoice_id).with_for_update())


def start_checkout(db, organization_id, invoice_id, expires_at):
    settings = test_settings()
    if not settings or settings.organization_id != organization_id:
        raise HTTPException(403, 'Razorpay Test Mode is unavailable for this business.')

    # Persist a stable reference before calling the provider so a lost response
    # can be recovered by looking up the reference on the next attempt.
    with mutation(db):
        invoice = locked_invoice(db, organization_id, invoice_id)
        if invoice is None:
            raise HTTPException(404, 'Private invoice is unavailable')
        balance = invoice_positions(db, organization_id, [invoice])[invoice.id]['outstanding_paise']
        dispute = db.scalar(select(InvoiceDispute).where(
            InvoiceDispute.organization_id == organization_id, InvoiceDispute.invoice_id == invoice_id))
        if not test_payment_available(organization_id, balance, dispute, expires_at):
            raise HTTPException(409, 'This invoice is currently unavailable for test checkout.')
        now = int(datetime.now(timezone.utc).timestamp())
        checkout = db.scalar(select(RazorpayCheckout).where(
            RazorpayCheckout.organization_id == organization_id, RazorpayCheckout.invoice_id == invoice_id,
            RazorpayCheckout.expires_at > now,
        ).order_by(RazorpayCheckout.expires_at.desc()).limit(1))
        if checkout is None:
            checkout = RazorpayCheckout(organization_id=organization_id, invoice_id=invoice_id,
                                        account_id=settings.account_id, amount_paise=balance,
                                        expires_at=min(now + LINK_DURATION, int(expires_at.timestamp())))
            db.add(checkout)
            db.flush()
        if checkout.amount_paise != balance or checkout.account_id != settings.account_id:
            raise HTTPException(409, 'The previous checkout is out of date. Wait for it to expire before retrying.')
        if checkout.provider_payment_id:
            raise HTTPException(409, 'Refresh this invoice to check the latest payment status.')
        checkout_id, invoice_number = checkout.id, invoice.invoice_number

    with mutation(db):
        invoice = locked_invoice(db, organization_id, invoice_id)
        checkout = db.scalar(select(RazorpayCheckout).where(
            RazorpayCheckout.id == checkout_id).with_for_update())
        if (checkout.provider_payment_id or checkout.expires_at <= datetime.now(timezone.utc).timestamp()
                or invoice_positions(db, organization_id, [invoice])[invoice_id]['outstanding_paise'] != checkout.amount_paise):
            raise HTTPException(409, 'Refresh this invoice to check the latest payment status.')
        if not checkout.checkout_url:
            link = provider_link(settings, checkout, invoice_number)
            if link.get('status') == 'paid':
                raise HTTPException(409, 'Razorpay received the payment. Refresh once it is confirmed.')
            if (not valid_id(link.get('id'), 'plink') or link.get('reference_id') != checkout.id
                    or link.get('amount') != checkout.amount_paise or link.get('currency') != 'INR'
                    or link.get('expire_by') != checkout.expires_at
                    or link.get('status') != 'created' or not valid_checkout_url(link.get('short_url'))):
                raise HTTPException(502, 'Razorpay returned an unavailable checkout.')
            checkout.provider_link_id = link['id']
            checkout.checkout_url = link['short_url']
            record_event(db, organization_id, 'razorpay-test', 'razorpay.checkout_created', checkout.id)
        return {'checkout_url': checkout.checkout_url, 'expires_at': checkout.expires_at}


def valid_checkout_url(value):
    if not isinstance(value, str) or not 0 < len(value) <= 512 or any(c.isspace() for c in value):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme == 'https' and parsed.netloc in {'rzp.io', 'razorpay.com'} and bool(parsed.path)


async def signed_event(request: Request):
    settings = test_settings()
    if not settings:
        raise HTTPException(404, 'Razorpay Test Mode is unavailable.')
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 128_000:
            raise HTTPException(413, 'Webhook is too large.')
        raw.extend(chunk)
    signature = request.headers.get('X-Razorpay-Signature', '')
    expected = hmac.new(settings.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not re.fullmatch(r'[a-f0-9]{64}', signature) or not hmac.compare_digest(signature, expected):
        raise HTTPException(401, 'Invalid webhook signature.')
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeError):
        raise HTTPException(400, 'Invalid webhook payload.') from None
    if not isinstance(event, dict) or event.get('account_id') != settings.account_id:
        raise HTTPException(403, 'Unexpected Razorpay account.')
    return settings, event


@router.post('/razorpay/test')
def payment_webhook(db: Db, delivery=Depends(signed_event)):
    settings, event = delivery
    if event.get('event') != 'payment_link.paid':
        return {'status': 'ignored'}
    try:
        link = event['payload']['payment_link']['entity']
        payment = event['payload']['payment']['entity']
        reference = link['reference_id']
        link_id, payment_id = link['id'], payment['id']
    except (KeyError, TypeError):
        raise HTTPException(400, 'Incomplete payment event.') from None
    if (not isinstance(reference, str) or len(reference) != 36
            or not valid_id(link_id, 'plink') or not valid_id(payment_id, 'pay')):
        return {'status': 'ignored'}

    with mutation(db):
        attempt = db.get(RazorpayCheckout, reference)
        if not attempt or attempt.organization_id != settings.organization_id or attempt.account_id != settings.account_id:
            return {'status': 'ignored'}
        invoice = locked_invoice(db, attempt.organization_id, attempt.invoice_id)
        db.refresh(attempt, with_for_update=True)
        if (invoice is None or attempt.provider_link_id not in {None, link_id}
                or link.get('status') != 'paid' or payment.get('status') != 'captured'
                or link.get('currency') != 'INR' or payment.get('currency') != 'INR'
                or link.get('amount') != attempt.amount_paise or link.get('amount_paid') != attempt.amount_paise
                or payment.get('amount') != attempt.amount_paise
                or not link.get('order_id') or link['order_id'] != payment.get('order_id')):
            raise HTTPException(409, 'Payment does not match the stored checkout.')
        if attempt.provider_payment_id == payment_id:
            return {'status': 'already_recorded'}
        if attempt.provider_payment_id:
            raise HTTPException(409, 'Checkout already has a recorded payment.')
        # Captured funds remain a receipt if adjustments reduced the balance.
        # The ledger represents the excess as customer credit.
        receipt = Payment(organization_id=attempt.organization_id, invoice_id=attempt.invoice_id,
                          amount_paise=attempt.amount_paise, idempotency_key=RAZORPAY_TEST_PAYMENT_PREFIX + payment_id)
        db.add(receipt)
        attempt.provider_link_id = link_id
        attempt.provider_payment_id = payment_id
        db.flush()
        record_event(db, attempt.organization_id, 'razorpay-test', 'payment.razorpay_test_captured', receipt.id)
        return {'status': 'recorded'}
