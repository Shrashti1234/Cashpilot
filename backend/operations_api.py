"""Authorized catalogue, stock, estimates, purchase orders and tax drafts."""
from contextlib import contextmanager
from datetime import date
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import record_event
from auth_identity import get_verified_identity
from intelligence_api import today
from operations import BusinessProfile, Product, StockMovement, TradeDocument, calculate_lines, post_stock, stock_balance
from saas_api import get_saas_session
from saas_domain import Customer, TenantAccessDenied, create_invoice, require_member, lock_organization

router = APIRouter(prefix='/api/v1/organizations/{organization_id}/operations', tags=['operations'])
Identity = Annotated[str, Depends(get_verified_identity)]
Db = Annotated[Session, Depends(get_saas_session)]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


def check_registration(gstin, state):
    if not re.fullmatch(r'\d{2}', state) or not 1 <= int(state) <= 38:
        raise ValueError('Enter a supported two-digit Indian state/UT code')
    if gstin and (not re.fullmatch(r'\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]', gstin) or gstin[:2] != state):
        raise ValueError('GSTIN format or state prefix does not match; registration is not verified online')


class ProfileInput(StrictInput):
    legal_name: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1, max_length=1000)
    gstin: str = Field(default='', max_length=15)
    state_code: str = Field(min_length=2, max_length=2)
    require_approval: bool = False

    @model_validator(mode='after')
    def validate_registration(self):
        check_registration(self.gstin, self.state_code)
        return self


class ProductInput(StrictInput):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=16)
    hsn_sac: str = Field(default='', pattern=r'^\d{4,8}$|^$')
    unit_price_paise: int = Field(ge=0, le=1_000_000_000, strict=True)
    tax_rate_bps: int = Field(ge=0, le=10000, strict=True)
    track_stock: bool = True
    reorder_milliunits: int = Field(default=0, ge=0, le=1_000_000_000, strict=True)
    active: bool = True


class StockInput(StrictInput):
    product_id: str = Field(min_length=1, max_length=36)
    quantity_milliunits: int = Field(ge=-1_000_000_000, le=1_000_000_000, strict=True)
    reference: str = Field(min_length=1, max_length=160)
    request_key: str = Field(min_length=1, max_length=80)

    @model_validator(mode='after')
    def nonzero(self):
        if self.quantity_milliunits == 0:
            raise ValueError('Stock movement must be nonzero')
        return self


class PartyInput(StrictInput):
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1, max_length=1000)
    gstin: str = Field(default='', max_length=15)
    state_code: str = Field(min_length=2, max_length=2)
    place_of_supply: str = Field(min_length=2, max_length=2)

    @model_validator(mode='after')
    def valid_registration(self):
        check_registration(self.gstin, self.state_code)
        check_registration('', self.place_of_supply)
        return self


class LineInput(StrictInput):
    product_id: str | None = Field(default=None, min_length=1, max_length=36)
    description: str = Field(min_length=1, max_length=300)
    hsn_sac: str = Field(default='', pattern=r'^\d{4,8}$|^$')
    unit: str = Field(min_length=1, max_length=16)
    quantity_milliunits: int = Field(gt=0, le=1_000_000, strict=True)
    unit_price_paise: int = Field(ge=0, le=1_000_000_000, strict=True)
    discount_paise: int = Field(default=0, ge=0, le=1_000_000_000, strict=True)
    tax_rate_bps: int = Field(ge=0, le=10000, strict=True)
    cess_rate_bps: int = Field(default=0, ge=0, le=10000, strict=True)


class DocumentInput(StrictInput):
    kind: str = Field(pattern=r'^(estimate|purchase_order|invoice)$')
    number: str = Field(min_length=1, max_length=16, pattern=r'^[A-Za-z0-9/-]+$')
    customer_id: str | None = Field(default=None, min_length=1, max_length=36)
    issue_date: date
    due_date: date
    party: PartyInput
    lines: list[LineInput] = Field(min_length=1, max_length=100)
    notes: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def valid_dates(self):
        if not date(2000, 1, 1) <= self.issue_date <= today() or not self.issue_date <= self.due_date:
            raise ValueError('Issue date must be today or earlier; due date must follow issue date')
        if self.kind == 'invoice' and not self.customer_id:
            raise ValueError('An invoice must reference a customer in this business')
        return self


class IssueInput(StrictInput):
    tax_reviewed: bool = False


class ReceiptInput(StrictInput):
    line_index: int = Field(ge=0, le=99, strict=True)
    quantity_milliunits: int = Field(gt=0, le=1_000_000, strict=True)
    request_key: str = Field(min_length=1, max_length=80)


def authorize(db, identity, organization_id, write=False, admin=False):
    try:
        member = require_member(db, identity, organization_id, write=write)
        if admin and member.role not in {'owner', 'admin'}:
            raise TenantAccessDenied()
        return member
    except TenantAccessDenied:
        raise HTTPException(403, 'Forbidden') from None


@contextmanager
def mutation(db):
    try:
        yield
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'This identifier already exists or the related record changed. Refresh and retry.') from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from None


def profile_out(p):
    return {k: getattr(p, k) for k in ProfileInput.model_fields}


def product_out(p, balance):
    return {'id': p.id, **{k: getattr(p, k) for k in ProductInput.model_fields},
            'stock_milliunits': balance, 'low_stock': p.track_stock and balance <= p.reorder_milliunits}


def document_out(d):
    return {k: (str(getattr(d, k)) if k in {'issue_date', 'due_date'} else getattr(d, k)) for k in
            ['id', 'kind', 'number', 'status', 'customer_id', 'invoice_id', 'issue_date', 'due_date',
             'party', 'supplier', 'lines', 'totals', 'received', 'notes', 'created_by', 'approved_by']}


def get_document(db, org, doc_id):
    doc = db.scalar(select(TradeDocument).where(TradeDocument.organization_id == org,
                                               TradeDocument.id == doc_id).with_for_update())
    if doc is None:
        raise HTTPException(404, 'Document not found')
    return doc


@router.get('/profile')
def get_profile(organization_id: str, identity: Identity, db: Db):
    authorize(db, identity, organization_id)
    p = db.get(BusinessProfile, organization_id)
    return {'profile': profile_out(p) if p else None}


@router.post('/profile')
def save_profile(organization_id: str, payload: ProfileInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, admin=True)
    with mutation(db):
        lock_organization(db, organization_id)
        p = db.get(BusinessProfile, organization_id)
        if p is None:
            p = BusinessProfile(organization_id=organization_id)
            db.add(p)
        for key, value in payload.model_dump().items():
            setattr(p, key, value)
        record_event(db, organization_id, identity, 'business_profile.updated', organization_id)
    return {'profile': profile_out(p)}


@router.get('/products')
def list_products(organization_id: str, identity: Identity, db: Db):
    authorize(db, identity, organization_id)
    balances = dict(db.execute(select(StockMovement.product_id, func.sum(StockMovement.quantity_milliunits)).where(
        StockMovement.organization_id == organization_id).group_by(StockMovement.product_id)).all())
    products = db.scalars(select(Product).where(Product.organization_id == organization_id).order_by(Product.name))
    return {'products': [product_out(p, balances.get(p.id, 0)) for p in products]}


@router.post('/products', status_code=201)
def add_product(organization_id: str, payload: ProductInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, write=True)
    with mutation(db):
        p = Product(organization_id=organization_id, **payload.model_dump())
        db.add(p)
        db.flush()
        record_event(db, organization_id, identity, 'product.created', p.id)
    return product_out(p, 0)


@router.post('/products/{product_id}')
def edit_product(organization_id: str, product_id: str, payload: ProductInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, write=True)
    with mutation(db):
        p = db.scalar(select(Product).where(Product.organization_id == organization_id,
                                            Product.id == product_id).with_for_update())
        if p is None:
            raise HTTPException(404, 'Product not found')
        if p.track_stock != payload.track_stock and db.scalar(select(StockMovement.id).where(
                StockMovement.organization_id == organization_id, StockMovement.product_id == product_id).limit(1)):
            raise ValueError('Stock tracking cannot change after a movement exists')
        for key, value in payload.model_dump().items():
            setattr(p, key, value)
        record_event(db, organization_id, identity, 'product.updated', p.id)
    return product_out(p, stock_balance(db, organization_id, product_id))


@router.get('/stock')
def list_stock(organization_id: str, identity: Identity, db: Db):
    authorize(db, identity, organization_id)
    rows = db.scalars(select(StockMovement).where(StockMovement.organization_id == organization_id)
                      .order_by(StockMovement.created_at.desc(), StockMovement.id).limit(1000))
    return {'movements': [{k: getattr(m, k) for k in ['id', 'product_id', 'quantity_milliunits', 'reason', 'reference', 'created_at']} for m in rows]}


@router.post('/stock', status_code=201)
def adjust_stock(organization_id: str, payload: StockInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, admin=True)
    with mutation(db):
        m = post_stock(db, organization_id=organization_id, product_id=payload.product_id,
            quantity=payload.quantity_milliunits, reason='adjustment', reference=payload.reference,
            request_key='manual:' + payload.request_key, actor_id=identity)
        record_event(db, organization_id, identity, 'stock.adjusted_or_replayed', m.id)
    return {'id': m.id, 'stock_milliunits': stock_balance(db, organization_id, payload.product_id)}


@router.get('/documents')
def list_documents(organization_id: str, identity: Identity, db: Db):
    authorize(db, identity, organization_id)
    rows = db.scalars(select(TradeDocument).where(TradeDocument.organization_id == organization_id)
                      .order_by(TradeDocument.created_at.desc()).limit(500))
    return {'documents': [document_out(d) for d in rows]}


@router.post('/documents', status_code=201)
def add_document(organization_id: str, payload: DocumentInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, write=True)
    with mutation(db):
        profile = db.get(BusinessProfile, organization_id)
        if profile is None:
            raise ValueError('Save the business tax profile before creating documents')
        if payload.customer_id and db.scalar(select(Customer.id).where(
                Customer.organization_id == organization_id, Customer.id == payload.customer_id)) is None:
            raise ValueError('Customer does not belong to this business')
        lines = [line.model_dump() for line in payload.lines]
        for line in lines:
            if line['product_id']:
                p = db.scalar(select(Product).where(Product.organization_id == organization_id,
                                                    Product.id == line['product_id'], Product.active.is_(True)))
                if p is None:
                    raise ValueError('Choose an active product from this business')
                line['track_stock'] = p.track_stock
            else:
                line['track_stock'] = False
        supplier_state = payload.party.state_code if payload.kind == 'purchase_order' else profile.state_code
        calculated, totals = calculate_lines(lines, supplier_state, payload.party.place_of_supply)
        d = TradeDocument(organization_id=organization_id, kind=payload.kind, number=payload.number,
            status='draft', customer_id=payload.customer_id, issue_date=payload.issue_date,
            due_date=payload.due_date, party=payload.party.model_dump(), supplier=profile_out(profile),
            lines=calculated, totals=totals, notes=payload.notes, created_by=identity, received={})
        db.add(d)
        db.flush()
        record_event(db, organization_id, identity, 'document.drafted', d.id)
    return document_out(d)


@router.post('/documents/{document_id}/approve')
def approve_document(organization_id: str, document_id: str, identity: Identity, db: Db):
    authorize(db, identity, organization_id, admin=True)
    with mutation(db):
        d = get_document(db, organization_id, document_id)
        if d.created_by == identity:
            raise ValueError('A different owner or administrator must approve this document')
        if d.status != 'draft':
            raise ValueError('Only a draft can be approved')
        d.status, d.approved_by = 'approved', identity
        record_event(db, organization_id, identity, 'document.approved', d.id)
    return document_out(d)


@router.post('/documents/{document_id}/issue')
def issue_document(organization_id: str, document_id: str, payload: IssueInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, write=True)
    with mutation(db):
        d = get_document(db, organization_id, document_id)
        if d.status == 'issued':
            return document_out(d)
        if d.status not in {'draft', 'approved'}:
            raise ValueError('This document cannot be issued')
        profile = db.scalar(select(BusinessProfile).where(BusinessProfile.organization_id == organization_id).with_for_update())
        if profile.require_approval and (d.status != 'approved' or not d.approved_by or d.approved_by == d.created_by):
            raise ValueError('Independent approval is required by business policy')
        if not payload.tax_reviewed:
            raise ValueError('Review the amounts, tax classification and registration details before issuing')
        if d.kind == 'invoice':
            if any(l['tax_rate_bps'] or l['cess_rate_bps'] for l in d.lines) and not d.supplier['gstin']:
                raise ValueError('A supplier GSTIN is required before issuing a tax-charging invoice')
            if any((l['tax_rate_bps'] or l['cess_rate_bps']) and not l['hsn_sac'] for l in d.lines):
                raise ValueError('Enter HSN/SAC for each taxable line before issuing')
            invoice = create_invoice(db, user_id=identity, organization_id=organization_id,
                customer_id=d.customer_id, invoice_number=d.number, due_date=d.due_date,
                total_paise=d.totals['total_paise'])
            d.invoice_id = invoice.id
            # Stable lock order prevents two multi-product issues deadlocking.
            for index, line in sorted(enumerate(d.lines), key=lambda pair: pair[1]['product_id'] or ''):
                if line['track_stock']:
                    post_stock(db, organization_id=organization_id, product_id=line['product_id'],
                        quantity=-line['quantity_milliunits'], reason='invoice_issue', reference=d.id,
                        request_key=f'issue:{d.id}:{index}', actor_id=identity)
        d.status = 'issued'
        record_event(db, organization_id, identity, 'document.issued', d.id)
    return document_out(d)


@router.post('/documents/{document_id}/cancel')
def cancel_document(organization_id: str, document_id: str, identity: Identity, db: Db):
    authorize(db, identity, organization_id, write=True)
    with mutation(db):
        d = get_document(db, organization_id, document_id)
        if d.status == 'issued' and (d.kind == 'invoice' or any(d.received.values())):
            raise ValueError('Issued invoices and received purchase orders need a separate reversal workflow')
        if d.status == 'cancelled':
            raise ValueError('Document is already cancelled')
        d.status = 'cancelled'
        record_event(db, organization_id, identity, 'document.cancelled', d.id)
    return document_out(d)


@router.post('/documents/{document_id}/receive')
def receive_purchase(organization_id: str, document_id: str, payload: ReceiptInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, write=True)
    with mutation(db):
        d = get_document(db, organization_id, document_id)
        if d.kind != 'purchase_order' or d.status != 'issued':
            raise ValueError('Receive stock against an issued purchase order')
        if payload.line_index >= len(d.lines):
            raise ValueError('Unknown purchase-order line')
        line = d.lines[payload.line_index]
        if not line['track_stock']:
            raise ValueError('This line is not a stock-tracked product')
        key = 'receipt:' + payload.request_key
        prior = db.scalar(select(StockMovement).where(StockMovement.organization_id == organization_id,
                                                      StockMovement.request_key == key))
        reference = f'{d.id}:{payload.line_index}'
        received = dict(d.received)
        index = str(payload.line_index)
        if not prior and received.get(index, 0) + payload.quantity_milliunits > line['quantity_milliunits']:
            raise ValueError('Receipt exceeds the remaining ordered quantity')
        post_stock(db, organization_id=organization_id, product_id=line['product_id'],
            quantity=payload.quantity_milliunits, reason='purchase_receipt', reference=reference,
            request_key=key, actor_id=identity)
        if not prior:
            received[index] = received.get(index, 0) + payload.quantity_milliunits
            d.received = received
            record_event(db, organization_id, identity, 'purchase.received', d.id)
    return document_out(d)
