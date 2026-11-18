"""Immutable forecast snapshots and explicit, revision-sensitive actual reviews."""
from datetime import date,datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
from sqlalchemy import BigInteger,Date,DateTime,ForeignKeyConstraint,Index,JSON,String,UniqueConstraint,Integer,CheckConstraint,select
from sqlalchemy.orm import Mapped,mapped_column
from audit import record_event
from cash_ledger import CashEntry
from intelligence import expense_projection,model_bundle,simulate
from saas_domain import SaaSBase,new_id,require_member,lock_organization


class ForecastSnapshot(SaaSBase):
    __tablename__='saas_forecast_snapshots'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    as_of:Mapped[date]=mapped_column(Date)
    request_key:Mapped[str]=mapped_column(String(80))
    actor_id:Mapped[str]=mapped_column(String(200))
    opening_paise:Mapped[int|None]=mapped_column(BigInteger,nullable=True)
    threshold_paise:Mapped[int]=mapped_column(BigInteger)
    model_sha256:Mapped[str]=mapped_column(String(64))
    input_sha256:Mapped[str]=mapped_column(String(64))
    payload:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(ForeignKeyConstraint(['organization_id'],['saas_organizations.id']),UniqueConstraint('organization_id','id'),UniqueConstraint('organization_id','request_key'),Index('ix_forecast_snapshots_org_date','organization_id','as_of'),CheckConstraint('threshold_paise >= 0'))


class ForecastReview(SaaSBase):
    __tablename__='saas_forecast_reviews'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id:Mapped[str]=mapped_column(String(36))
    snapshot_id:Mapped[str]=mapped_column(String(36))
    horizon_days:Mapped[int]=mapped_column(Integer)
    actual_sha256:Mapped[str]=mapped_column(String(64))
    actual_paise:Mapped[int]=mapped_column(BigInteger)
    note:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[str]=mapped_column(String(200))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(ForeignKeyConstraint(['organization_id','snapshot_id'],['saas_forecast_snapshots.organization_id','saas_forecast_snapshots.id']),CheckConstraint('horizon_days IN (7,30,90)'),Index('ix_forecast_reviews_org_snapshot','organization_id','snapshot_id'))


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def create_snapshot(db,org,actor,as_of,request_key,opening=None,threshold=0):
    require_member(db,actor,org,write=True);lock_organization(db,org)
    prior=db.scalar(select(ForecastSnapshot).where(ForecastSnapshot.organization_id==org,ForecastSnapshot.request_key==request_key))
    if prior:
        if prior.opening_paise!=opening or prior.threshold_paise!=threshold:raise ValueError('Forecast key was already used for different assumptions')
        return prior
    records=list(db.scalars(select(CashEntry).where(CashEntry.organization_id==org).order_by(CashEntry.entry_date,CashEntry.id).limit(10001)))
    if len(records)>10000:raise ValueError('Forecast snapshots support up to 10,000 cash entries in this release')
    entries=[{k:getattr(e,k) for k in ['id','entry_date','direction','status','amount_paise']} for e in records]
    expense,_,method,observed=expense_projection(entries,as_of,90)
    if sum(expense)>9_007_199_254_740_991:raise ValueError('Projected expense totals exceed the supported display precision')
    days={e['entry_date'] for e in entries if e['status']=='actual' and e['direction']=='out' and as_of-timedelta(days=365)<=e['entry_date']<as_of}
    warnings=['Models are trained on synthetic data only; real-world financial accuracy is unvalidated.','Missing expense dates are treated as zero. Incomplete records can materially change a forecast.']
    if method!='trained_ridge_expenses':warnings.append('Insufficient recent expense history for the learned model. The forecast uses a trailing mean or no-history fallback.')
    payload={'expense_method':method,'history_days':observed,'recorded_expense_dates':len(days),'provenance':model_bundle()['provenance'],'model_version':model_bundle()['version'],
        'expense_points':[{'date':str(as_of+timedelta(days=i)),'amount_paise':value} for i,value in enumerate(expense)],
        'expense_totals':{str(h):sum(expense[:h]) for h in [7,30,90]},'cash_baseline':None,'attention':[],'warnings':warnings}
    source={'entries':entries,'as_of':as_of,'opening_paise':opening,'threshold_paise':threshold}
    if opening is not None:
        # Import lazily to keep the domain models independent of API composition.
        from intelligence_api import tenant_inputs
        _,invoices=tenant_inputs(db,org,as_of)
        result=simulate(opening,entries,invoices,as_of,90,paths=100)
        if any(abs(p[key])>9_007_199_254_740_991 for p in result['baseline']['points'] for key in ['p10_paise','median_paise','p90_paise']):raise ValueError('Projected cash values exceed the supported display precision')
        payload['cash_baseline']=result['baseline'];source['invoices']=invoices
        first=next((p['date'] for p in result['baseline']['points'] if p['median_paise']<threshold),None)
        if first:payload['attention'].append({'code':'conditional_cash_threshold','date':first,'detail':'The simulated median balance is below the supplied threshold. Review assumptions in Decision Lab; this is not a bank balance or guaranteed outcome.'})
    row=ForecastSnapshot(organization_id=org,as_of=as_of,request_key=request_key,actor_id=actor,opening_paise=opening,threshold_paise=threshold,
        model_sha256=hashlib.sha256((Path(__file__).parent/'models/intelligence.json').read_bytes()).hexdigest(),input_sha256=digest(source),payload=payload)
    db.add(row);db.flush();record_event(db,org,actor,'forecast.snapshot_created',row.id);return row


def actual_window(db,org,snapshot,horizon):
    end=snapshot.as_of+timedelta(days=horizon)
    rows=list(db.scalars(select(CashEntry).where(CashEntry.organization_id==org,CashEntry.entry_date>=snapshot.as_of,CashEntry.entry_date<end,CashEntry.direction=='out',CashEntry.status=='actual').order_by(CashEntry.id)))
    return rows,sum(e.amount_paise for e in rows),digest([{k:getattr(e,k) for k in ['id','entry_date','amount_paise']} for e in rows])


def evaluate_snapshot(db,org,snapshot,as_of):
    reviews=list(db.scalars(select(ForecastReview).where(ForecastReview.organization_id==org,ForecastReview.snapshot_id==snapshot.id).order_by(ForecastReview.created_at.desc(),ForecastReview.id.desc())))
    latest={}
    for review in reviews:latest.setdefault(review.horizon_days,review)
    results=[]
    for h in [7,30,90]:
        end=snapshot.as_of+timedelta(days=h);closed=end<=as_of;predicted=snapshot.payload['expense_totals'][str(h)]
        rows,actual,current_hash=actual_window(db,org,snapshot,h) if closed else ([],None,None)
        review=latest.get(h);confirmed=bool(closed and review and review.actual_sha256==current_hash)
        difference=predicted-actual if closed else None
        results.append({'horizon_days':h,'period_end':str(end-timedelta(days=1)),'closed':closed,'forecast_paise':predicted,'recorded_actual_paise':actual,'recorded_expense_dates':len({e.entry_date for e in rows}),
            'difference_paise':difference,'coverage_confirmed':confirmed,'review_stale':bool(review and not confirmed),
            'absolute_percentage_error':round(abs(difference)/actual*100,2) if confirmed and actual else None,
            'latest_review_note':review.note if review else None})
    return results
