"""Invoice-scoped payment commitments; a promise is never a receipt."""
from datetime import date,datetime,timezone

from sqlalchemy import BigInteger,CheckConstraint,Date,DateTime,ForeignKeyConstraint,Index,String,UniqueConstraint,select,func,text,and_
from sqlalchemy.orm import Mapped,mapped_column

from audit import record_event
from saas_domain import SaaSBase,Invoice,Payment,new_id,invoice_positions


class PaymentPromise(SaaSBase):
    __tablename__='saas_payment_promises'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    invoice_id:Mapped[str]=mapped_column(String(36))
    amount_paise:Mapped[int]=mapped_column(BigInteger)
    promised_date:Mapped[date]=mapped_column(Date)
    note:Mapped[str]=mapped_column(String(1000))
    status:Mapped[str]=mapped_column(String(12),default='pending')
    cancellation_note:Mapped[str|None]=mapped_column(String(1000),nullable=True)
    actor_id:Mapped[str]=mapped_column(String(200))
    source:Mapped[str]=mapped_column(String(12),default='member')
    request_key:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(
        ForeignKeyConstraint(['organization_id','invoice_id'],['saas_invoices.organization_id','saas_invoices.id']),
        UniqueConstraint('organization_id','request_key'),
        CheckConstraint('amount_paise > 0 AND amount_paise <= 2000000000'),
        CheckConstraint("status IN ('pending','fulfilled','cancelled')"),
        CheckConstraint("source IN ('member','buyer_link')"),
        Index('ix_promises_org_invoice','organization_id','invoice_id'),
        Index('uq_promises_pending_invoice','organization_id','invoice_id',unique=True,
              postgresql_where=text("status='pending'"),sqlite_where=text("status='pending'")),
    )


def received_since(db,p):
    return db.scalar(select(func.coalesce(func.sum(Payment.amount_paise),0)).where(
        Payment.organization_id==p.organization_id,Payment.invoice_id==p.invoice_id,Payment.created_at>=p.created_at))


def unfulfilled_promises(db,organization_id):
    rows=db.execute(select(PaymentPromise.invoice_id,PaymentPromise.promised_date,PaymentPromise.amount_paise).outerjoin(
        Payment,and_(Payment.organization_id==PaymentPromise.organization_id,Payment.invoice_id==PaymentPromise.invoice_id,
                     Payment.created_at>=PaymentPromise.created_at)).where(PaymentPromise.organization_id==organization_id,
        PaymentPromise.status=='pending').group_by(PaymentPromise.id,PaymentPromise.invoice_id,PaymentPromise.promised_date,
        PaymentPromise.amount_paise).having(func.coalesce(func.sum(Payment.amount_paise),0)<PaymentPromise.amount_paise))
    return {r.invoice_id:{'date':r.promised_date,'amount_paise':r.amount_paise} for r in rows}


def promise_out(p,received,as_of):
    state=p.status
    if state=='pending':state='fulfilled' if received>=p.amount_paise else 'overdue' if p.promised_date<as_of else 'pending'
    return {'id':p.id,'invoice_id':p.invoice_id,'amount_paise':p.amount_paise,'promised_date':p.promised_date,
            'note':p.note,'state':state,'received_since_paise':received,'created_at':p.created_at if p.created_at.tzinfo else p.created_at.replace(tzinfo=timezone.utc),
            'cancellation_note':p.cancellation_note,'source':p.source}


def create_promise(db,organization_id,invoice_id,actor_id,amount,promised_date,note,request_key,source='member'):
    # Every promise/payment writer locks the invoice before inspecting balances.
    inv=db.scalar(select(Invoice).where(Invoice.organization_id==organization_id,Invoice.id==invoice_id).with_for_update())
    if inv is None:raise ValueError('Invoice not found')
    replay=db.scalar(select(PaymentPromise).where(PaymentPromise.organization_id==organization_id,PaymentPromise.request_key==request_key))
    if replay:
        if (replay.invoice_id,replay.amount_paise,replay.promised_date,replay.note)!=(invoice_id,amount,promised_date,note):raise ValueError('Promise key was already used for different details')
        return replay
    prior=db.scalar(select(PaymentPromise).where(PaymentPromise.organization_id==organization_id,PaymentPromise.invoice_id==invoice_id,PaymentPromise.status=='pending').with_for_update())
    if prior:
        if received_since(db,prior)>=prior.amount_paise:
            prior.status='fulfilled';record_event(db,organization_id,actor_id,'promise.fulfilled',prior.id)
            db.flush()
        elif (prior.amount_paise,prior.promised_date,prior.note)==(amount,promised_date,note):return prior
        else:raise ValueError('An active promise already exists. Ask the business to review or cancel it before replacing it.')
    position=invoice_positions(db,organization_id,[inv])[inv.id]
    if amount>position['outstanding_paise']:raise ValueError('Promise exceeds the outstanding invoice balance')
    p=PaymentPromise(organization_id=organization_id,invoice_id=invoice_id,amount_paise=amount,
        promised_date=promised_date,note=note,actor_id=actor_id,source=source,request_key=request_key,status='pending')
    db.add(p);db.flush();record_event(db,organization_id,actor_id,'promise.recorded',p.id)
    return p
