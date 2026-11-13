from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from audit import record_event
from business_clock import india_today
from collection_tasks import CollectionTask
from financial_approvals import locked_writer
from operations_api import authorize, mutation
from saas_api import Db, Identity, build_collections_plan
from saas_domain import Invoice, Membership, invoice_positions

router = APIRouter(prefix='/api/v1/organizations/{organization_id}/collections/worklist')


class Assignment(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    assignee: str = Field(min_length=1, max_length=200)
    follow_up: date
    note: str = Field(default='', max_length=500)


@router.get('')
def worklist(organization_id: str, identity: Identity, db: Db):
    authorize(db, identity, organization_id)
    plan = build_collections_plan(organization_id, identity, db, limit=100)
    ids = [row['invoice_id'] for row in plan['actions']]
    members = set(db.scalars(select(Membership.user_id).where(Membership.organization_id == organization_id, Membership.active.is_(True), Membership.role != 'viewer')))
    tasks = {t.invoice_id: t for t in db.scalars(select(CollectionTask).where(CollectionTask.organization_id == organization_id, CollectionTask.invoice_id.in_(ids)))}
    refs = dict(db.execute(select(Invoice.id, Invoice.invoice_number).where(Invoice.organization_id == organization_id, Invoice.id.in_(ids))).all())
    for row in plan['actions']:
        task = tasks.get(row['invoice_id'])
        row['reference'] = refs.get(row['invoice_id'])
        row['task'] = {'assignee': task.assignee, 'follow_up': task.follow_up, 'note': task.note, 'active': task.assignee in members} if task else None
    return {**plan, 'members': sorted(members), 'me': identity}


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
