from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, func, or_, select

from audit import record_event
from business_clock import india_today
from collection_tasks import CollectionTask
from collections_intelligence import Receivable, collections_plan
from contacts import ContactRecord
from disputes import InvoiceDispute
from financial_approvals import locked_writer
from operations_api import authorize, mutation
from promises import unfulfilled_promises
from saas_api import Db, Identity
from saas_domain import Customer, Invoice, InvoiceMemo, InvoiceRefund, Membership, Payment, invoice_positions

router = APIRouter(prefix='/api/v1/organizations/{organization_id}/collections/worklist')


class Assignment(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    assignee: str = Field(min_length=1, max_length=200)
    follow_up: date
    note: str = Field(default='', max_length=500)


def _balance_component(model, *conditions):
    return select(func.coalesce(func.sum(model.amount_paise), 0)).where(
        model.organization_id == Invoice.organization_id, model.invoice_id == Invoice.id, *conditions
    ).correlate(Invoice).scalar_subquery()


@router.get('')
def worklist(organization_id: str, identity: Identity, db: Db,
             view: Literal['all', 'mine', 'due', 'unassigned'] = 'all',
             q: Annotated[str, Query(max_length=100)] = '',
             page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
             page_size: Annotated[int, Query(ge=1, le=50)] = 25):
    authorize(db, identity, organization_id)
    today = india_today()
    members_query = select(Membership.user_id).where(
        Membership.organization_id == organization_id, Membership.active.is_(True), Membership.role != 'viewer'
    )
    members = set(db.scalars(members_query))
    active_task = CollectionTask.assignee.in_(members_query)
    balance = (Invoice.total_paise + _balance_component(InvoiceMemo, InvoiceMemo.kind == 'debit')
               - _balance_component(InvoiceMemo, InvoiceMemo.kind == 'credit')
               - _balance_component(Payment) + _balance_component(InvoiceRefund))
    candidates = (select(Invoice.id.label('invoice_id'), Invoice.invoice_number, Invoice.due_date,
                         Invoice.customer_id, Customer.name.label('customer_name'), balance.label('balance'),
                         CollectionTask.assignee, CollectionTask.follow_up, CollectionTask.note)
                  .join(Customer, and_(Customer.organization_id == Invoice.organization_id, Customer.id == Invoice.customer_id))
                  .outerjoin(CollectionTask, and_(CollectionTask.organization_id == Invoice.organization_id, CollectionTask.invoice_id == Invoice.id))
                  .where(Invoice.organization_id == organization_id))
    if view == 'mine':
        candidates = candidates.where(CollectionTask.assignee == identity, active_task)
    elif view == 'due':
        candidates = candidates.where(CollectionTask.follow_up <= today, active_task)
    elif view == 'unassigned':
        candidates = candidates.where(or_(CollectionTask.assignee.is_(None), ~active_task))
    if term := q.strip():
        candidates = candidates.where(or_(Invoice.invoice_number.icontains(term, autoescape=True),
                                          Customer.name.icontains(term, autoescape=True)))
    candidates = candidates.subquery()
    opened = select(candidates).where(candidates.c.balance > 0)
    count = db.scalar(select(func.count()).select_from(candidates).where(candidates.c.balance > 0))
    # Scheduled actions due now come first; the rest are ordered by invoice due date.
    due_first = case((and_(candidates.c.follow_up <= today, candidates.c.assignee.in_(members_query)), 0), else_=1)
    records = db.execute(opened.order_by(due_first, candidates.c.due_date, candidates.c.invoice_id)
                         .offset((page - 1) * page_size).limit(page_size)).all()
    ids = [r.invoice_id for r in records]
    disputed = set(db.scalars(select(InvoiceDispute.invoice_id).where(
        InvoiceDispute.organization_id == organization_id, InvoiceDispute.invoice_id.in_(ids), InvoiceDispute.status != 'resolved')))
    contacted = dict(db.execute(select(ContactRecord.customer_id, func.max(ContactRecord.contact_date)).where(
        ContactRecord.organization_id == organization_id, ContactRecord.customer_id.in_({r.customer_id for r in records})
    ).group_by(ContactRecord.customer_id)).all())
    promises = unfulfilled_promises(db, organization_id, ids)
    recommendations = collections_plan([
        Receivable(r.invoice_id, r.customer_name, r.due_date, r.balance, r.invoice_id in disputed, contacted.get(r.customer_id),
                   promises.get(r.invoice_id, {}).get('date'), promises.get(r.invoice_id, {}).get('amount_paise'))
        for r in records], as_of=today, max_actions=page_size)
    by_id = {row['invoice_id']: row for row in recommendations['actions']}
    actions = [{**by_id[r.invoice_id], 'reference': r.invoice_number,
                'task': {'assignee': r.assignee, 'follow_up': r.follow_up, 'note': r.note, 'active': r.assignee in members}
                if r.assignee else None} for r in records]
    return {'as_of': today, 'actions': actions, 'members': sorted(members), 'me': identity,
            'page': page, 'page_size': page_size, 'total': count}


@router.post('/{invoice_id}')
def assign(organization_id: str, invoice_id: str, payload: Assignment, identity: Identity, db: Db):
    authorize(db, identity, organization_id, write=True)
    with mutation(db):
        member = locked_writer(db, organization_id, identity)
        invoice = db.scalar(select(Invoice).where(Invoice.organization_id == organization_id, Invoice.id == invoice_id).with_for_update())
        if not invoice:
            raise HTTPException(404, 'Invoice not found.')
        if not invoice_positions(db, organization_id, [invoice])[invoice_id]['outstanding_paise']:
            raise ValueError('Only open balances can have a follow-up.')
        if not india_today() <= payload.follow_up <= india_today() + timedelta(days=365):
            raise ValueError('Follow-up must be today or within the next year.')
        assignee = db.get(Membership, (organization_id, payload.assignee), populate_existing=True)
        if not assignee or not assignee.active or assignee.role == 'viewer':
            raise ValueError('Choose an active team member who can make changes.')
        task = db.get(CollectionTask, (organization_id, invoice_id))
        if member.role not in {'owner', 'admin'} and (payload.assignee != identity or task and task.assignee != identity):
            raise HTTPException(403, 'Only an owner or admin can reassign someone else’s follow-up.')
        if not task:
            task = CollectionTask(organization_id=organization_id, invoice_id=invoice_id)
            db.add(task)
        task.assignee, task.follow_up, task.note = payload.assignee, payload.follow_up, payload.note
        record_event(db, organization_id, identity, 'collection.follow_up_saved', invoice_id)
    return {'saved': True}
