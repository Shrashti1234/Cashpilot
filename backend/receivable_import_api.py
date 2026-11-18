"""Tenant-scoped preview and atomic import of invoice-level opening receivables."""
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from audit import record_event
from financial_approvals import locked_writer
from operations import BusinessProfile
from operations_api import authorize, mutation
from saas_api import Db, Identity
from saas_domain import Customer, Invoice, new_id

router = APIRouter(prefix='/api/v1/organizations/{organization_id}/receivable-import')


class FileInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(min_length=1, max_length=500_000)


class Columns(BaseModel):
    model_config = ConfigDict(extra='forbid')
    customer: str = Field(min_length=1, max_length=160)
    reference: str = Field(min_length=1, max_length=160)
    due: str = Field(min_length=1, max_length=160)
    amount: str = Field(min_length=1, max_length=160)


class MappedInput(FileInput):
    columns: Columns


class CommitInput(MappedInput):
    preview_digest: str = Field(pattern=r'^[0-9a-f]{64}$')


def read_csv(content):
    try:
        if '\x00' in content or len(content.encode('utf-8')) > 1_000_000:
            raise ValueError('Use a UTF-8 CSV file under 1 MB.')
        reader = csv.reader(io.StringIO(content.lstrip('\ufeff'), newline=''), strict=True)
        headers = [h.strip() for h in next(reader, [])]
        if not headers or len(headers) > 80 or any(not h or len(h) > 160 for h in headers) or len(set(headers)) != len(headers):
            raise ValueError('Use one header row with unique, nonempty column names (up to 80 columns).')
        rows = []
        while True:
            line = reader.line_num + 1
            values = next(reader, None)
            if values is None:
                break
            if any(v.strip() for v in values):
                rows.append((line, values))
            if len(rows) > 500:
                raise ValueError('Import at most 500 data rows per file.')
        if not rows:
            raise ValueError('The file contains no data rows.')
        return headers, rows
    except (csv.Error, UnicodeError) as exc:
        raise ValueError('Could not read this CSV. Check the encoding and quotation marks.') from exc


def parse_due(value):
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return date.fromisoformat(value)
    if re.fullmatch(r'\d{2}/\d{2}/\d{4}', value):
        return datetime.strptime(value, '%d/%m/%Y').date()
    raise ValueError('Invalid date')


def parse_amount(value):
    if len(value) > 18 or not re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3})(?:\.[0-9]{1,2})?', value):
        raise ValueError('Use a positive INR amount with up to two decimal places.')
    paise = int(Decimal(value.replace(',', '')) * 100)
    if not 0 < paise <= 2_000_000_000:
        raise ValueError('Opening amount must be above zero and at most INR 2 crore.')
    return paise


def preview_rows(db, org, payload):
    headers, source = read_csv(payload.content)
    names = [payload.columns.customer, payload.columns.reference, payload.columns.due, payload.columns.amount]
    if len(set(names)) != 4 or not set(names) <= set(headers):
        raise ValueError('Map the four fields to distinct CSV columns.')
    indices = [headers.index(name) for name in names]
    rows = []
    for line, values in source:
        row = {'row': line, 'status': 'ready', 'errors': []}
        rows.append(row)
        if len(values) != len(headers):
            row['errors'].append('Column count differs from the header.')
            continue
        name, reference, due, amount = (values[i].strip() for i in indices)
        row.update(customer=name[:160], reference=reference[:64])
        if not name or len(name) > 160 or not name.isprintable():
            row['errors'].append('Customer must contain 1–160 printable characters.')
        if not reference or len(reference) > 64 or not reference.isprintable():
            row['errors'].append('Reference must contain 1–64 printable characters.')
        try:
            row['due_date'] = parse_due(due).isoformat()
        except ValueError:
            row['errors'].append('Enter a valid due date in YYYY-MM-DD or DD/MM/YYYY.')
        try:
            row['amount_paise'] = parse_amount(amount)
        except ValueError as exc:
            row['errors'].append(str(exc))
    refs = Counter(row['reference'] for row in rows if 'reference' in row)
    existing = {inv.invoice_number: inv for inv in db.scalars(select(Invoice).where(Invoice.organization_id == org, Invoice.invoice_number.in_(list(refs))))}
    customers = defaultdict(list)
    for cid, name in db.execute(select(Customer.id, Customer.name).where(Customer.organization_id == org, Customer.name.in_({r['customer'] for r in rows if 'customer' in r}))):
        customers[name].append(cid)
    for row in rows:
        if not row['errors']:
            ref = row['reference']
            matches = customers[row['customer']]
            if refs[ref] > 1:
                row['errors'].append('Reference is repeated within this file.')
            elif ref in existing:
                inv = existing[ref]
                if inv.opening_receivable and inv.customer_id in matches and inv.due_date.isoformat() == row['due_date'] and inv.total_paise == row['amount_paise']:
                    row['status'] = 'duplicate'
                else:
                    row['errors'].append('Reference already exists with different details or is a CashPilot invoice.')
            elif len(matches) > 1:
                row['errors'].append('Multiple customers have this exact name. Resolve the ambiguity first.')
            else:
                row['customer_id'] = matches[0] if matches else None
        if row['errors']:
            row['status'] = 'error'
    profile = db.get(BusinessProfile, org, populate_existing=True)
    blocked = bool(profile and profile.require_approval)
    digest = hashlib.sha256(json.dumps([org, rows, blocked], sort_keys=True).encode()).hexdigest()
    return {'rows': rows, 'preview_digest': digest, 'blocked_by_approval': blocked,
            'ready': sum(r['status'] == 'ready' for r in rows), 'duplicates': sum(r['status'] == 'duplicate' for r in rows),
            'errors': sum(r['status'] == 'error' for r in rows), 'ready_paise': sum(r.get('amount_paise', 0) for r in rows if r['status'] == 'ready')}


@router.post('/inspect')
def inspect_file(organization_id: str, payload: FileInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, admin=True)
    try:
        headers, rows = read_csv(payload.content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {'headers': headers, 'row_count': len(rows)}


@router.post('/preview')
def preview(organization_id: str, payload: MappedInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, admin=True)
    try:
        return preview_rows(db, organization_id, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post('/commit')
def commit(organization_id: str, payload: CommitInput, identity: Identity, db: Db):
    authorize(db, identity, organization_id, admin=True)
    with mutation(db):
        locked_writer(db, organization_id, identity, admin=True)
        plan = preview_rows(db, organization_id, payload)
        if plan['blocked_by_approval'] or plan['errors']:
            raise ValueError('Import is blocked by approval policy or row errors. Review the preview.')
        if not plan['ready']:
            return {'imported': 0, 'duplicates': plan['duplicates']}
        if plan['preview_digest'] != payload.preview_digest:
            raise HTTPException(409, 'Records changed after preview. Preview the file again.')
        new_customers = {}
        for row in plan['rows']:
            if row['status'] != 'ready' or row['customer_id'] or row['customer'] in new_customers:
                continue
            name = row['customer']
            customer = Customer(id=new_id(), organization_id=organization_id, name=name)
            new_customers[name] = customer.id
            db.add(customer)
            record_event(db, organization_id, identity, 'customer.imported', customer.id)
        db.flush()
        for row in plan['rows']:
            if row['status'] != 'ready':
                continue
            inv = Invoice(id=new_id(), organization_id=organization_id, opening_receivable=True,
                          invoice_number=row['reference'], customer_id=row['customer_id'] or new_customers[row['customer']],
                          due_date=date.fromisoformat(row['due_date']), total_paise=row['amount_paise'])
            db.add(inv)
            record_event(db, organization_id, identity, 'invoice.opening_receivable_imported', inv.id)
    return {'imported': plan['ready'], 'duplicates': plan['duplicates']}
