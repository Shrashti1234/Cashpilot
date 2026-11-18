"""Bounded, idempotent recurrence: generate reviewable drafts, never post cash."""
import calendar
from datetime import date, timedelta

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, JSON, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from audit import record_event
from operations import TradeDocument
from saas_domain import SaaSBase, Organization, new_id, require_member,lock_organization


class RecurringRule(SaaSBase):
    __tablename__='saas_recurring_rules'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id: Mapped[str]=mapped_column(String(36),ForeignKey('saas_organizations.id'))
    name: Mapped[str]=mapped_column(String(100))
    prefix: Mapped[str]=mapped_column(String(5))
    frequency: Mapped[str]=mapped_column(String(8))
    interval: Mapped[int]=mapped_column(Integer)
    anchor_day: Mapped[int]=mapped_column(Integer)
    next_date: Mapped[date]=mapped_column(Date)
    end_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    terms_days: Mapped[int]=mapped_column(Integer)
    sequence: Mapped[int]=mapped_column(Integer,default=1)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    template: Mapped[dict]=mapped_column(JSON)
    created_by: Mapped[str]=mapped_column(String(200))
    __table_args__=(UniqueConstraint('organization_id','prefix'),
        CheckConstraint("frequency IN ('weekly','monthly')"),
        CheckConstraint('interval >= 1 AND interval <= 52'),
        CheckConstraint('anchor_day >= 1 AND anchor_day <= 31'),
        CheckConstraint('terms_days >= 0 AND terms_days <= 365'),
        CheckConstraint('sequence >= 1 AND sequence <= 10000'))


def advance(day:date,frequency:str,interval:int,anchor:int)->date:
    if frequency=='weekly':return day+timedelta(weeks=interval)
    offset=day.year*12+day.month-1+interval
    year,month=divmod(offset,12)
    return date(year,month+1,min(anchor,calendar.monthrange(year,month+1)[1]))


def generate_due(db:Session,organization_id:str,identity:str,as_of:date,limit=25):
    require_member(db,identity,organization_id,write=True)
    # Serialize runs within a business, including simultaneous manual/job runs.
    lock_organization(db,organization_id)
    rules=list(db.scalars(select(RecurringRule).where(RecurringRule.organization_id==organization_id,
        RecurringRule.active.is_(True),RecurringRule.next_date<=as_of).order_by(RecurringRule.next_date,RecurringRule.id).with_for_update()))
    created=[];errors=[]
    for rule in rules:
        if len(created)>=limit:break
        while rule.active and rule.next_date<=as_of and len(created)<limit:
            if (rule.end_date and rule.next_date>rule.end_date) or rule.sequence>9999:
                rule.active=False;break
            try:
                with db.begin_nested():
                    template=rule.template
                    number=f'{rule.prefix}{rule.next_date:%y%m%d}-{rule.sequence:04d}'
                    draft=TradeDocument(organization_id=organization_id,kind='invoice',number=number,status='draft',
                        customer_id=template['customer_id'],issue_date=rule.next_date,
                        due_date=rule.next_date+timedelta(days=rule.terms_days),party=template['party'],
                        supplier=template['supplier'],lines=template['lines'],totals=template['totals'],
                        received={},notes=template['notes'],created_by=identity)
                    db.add(draft);db.flush()
                    scheduled=rule.next_date
                    rule.next_date=advance(scheduled,rule.frequency,rule.interval,rule.anchor_day)
                    rule.sequence+=1
                    if (rule.end_date and rule.next_date>rule.end_date) or rule.sequence>9999:rule.active=False
                    record_event(db,organization_id,identity,'recurrence.draft_generated',draft.id)
                    db.flush()
                created.append({'id':draft.id,'number':draft.number,'scheduled_date':str(scheduled)})
            except (IntegrityError,ValueError,OverflowError):
                errors.append({'rule_id':rule.id,'rule_name':rule.name,'detail':'Could not generate this series. Check number conflicts and template references; no cycle was advanced.'})
                break
    remaining=any(r.active and r.next_date<=as_of for r in rules)
    return {'created':created,'errors':errors,'remaining_due':remaining,'limit':limit,
            'note':'Generated drafts require review and issue. No invoice, stock movement or payment was posted.'}
