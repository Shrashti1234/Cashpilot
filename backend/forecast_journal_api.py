from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from audit import record_event
from forecast_journal import ForecastSnapshot,ForecastReview,create_snapshot,actual_window,evaluate_snapshot
from intelligence_api import today
from operations_api import authorize,mutation
from request_limits import allow_action
from saas_api import Identity,Db
from saas_domain import lock_organization

router=APIRouter(prefix='/api/v1/organizations/{organization_id}/forecast-journal',tags=['forecast-monitoring'])
class SnapshotInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_key:str=Field(min_length=1,max_length=80)
    opening_paise:int|None=Field(default=None,ge=-1_000_000_000_000,le=1_000_000_000_000,strict=True)
    threshold_paise:int=Field(default=0,ge=0,le=1_000_000_000_000,strict=True)
class ReviewInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    horizon_days:int=Field(strict=True)
    note:str=Field(min_length=1,max_length=1000)
    confirmed_complete:bool=Field(default=False,strict=True)


def snapshot(db,org,snapshot_id):
    row=db.scalar(select(ForecastSnapshot).where(ForecastSnapshot.organization_id==org,ForecastSnapshot.id==snapshot_id))
    if not row:raise HTTPException(404,'Forecast snapshot not found')
    return row


def summary(row):return {k:getattr(row,k) for k in ['id','as_of','opening_paise','threshold_paise','created_at','model_sha256','input_sha256']}


@router.get('')
def snapshots(organization_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id)
    rows=db.scalars(select(ForecastSnapshot).where(ForecastSnapshot.organization_id==organization_id).order_by(ForecastSnapshot.created_at.desc()).limit(100))
    return {'snapshots':[{**summary(row),'expense_method':row.payload['expense_method'],'expense_totals':row.payload['expense_totals'],'attention':row.payload['attention']} for row in rows]}


@router.post('',status_code=201)
def save_snapshot(organization_id:str,payload:SnapshotInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True);allow_action(identity,'forecast-journal:'+organization_id,'forecast snapshots')
    with mutation(db):row=create_snapshot(db,organization_id,identity,today(),payload.request_key,payload.opening_paise,payload.threshold_paise)
    return {**summary(row),'payload':row.payload}


@router.get('/{snapshot_id}')
def snapshot_details(organization_id:str,snapshot_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id);row=snapshot(db,organization_id,snapshot_id)
    return {**summary(row),'payload':row.payload,'evaluation':evaluate_snapshot(db,organization_id,row,today()),'evaluation_as_of':today(),
        'note':'Compare against current recorded operating expenses only. Closed windows remain provisional until you confirm complete records; later record changes invalidate that review. Refunds and invoice payments are excluded.'}


@router.post('/{snapshot_id}/reviews',status_code=201)
def review_snapshot(organization_id:str,snapshot_id:str,payload:ReviewInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,write=True)
    if payload.horizon_days not in {7,30,90} or not payload.confirmed_complete:raise HTTPException(422,'Choose 7, 30 or 90 days and confirm the expense records are complete')
    with mutation(db):
        lock_organization(db,organization_id);row=snapshot(db,organization_id,snapshot_id)
        from datetime import timedelta
        if row.as_of+timedelta(days=payload.horizon_days)>today():raise ValueError('Wait until the complete forecast window has ended')
        _,actual,actual_hash=actual_window(db,organization_id,row,payload.horizon_days)
        review=ForecastReview(organization_id=organization_id,snapshot_id=row.id,horizon_days=payload.horizon_days,actual_sha256=actual_hash,actual_paise=actual,note=payload.note,actor_id=identity)
        db.add(review);db.flush();record_event(db,organization_id,identity,'forecast.actuals_reviewed',review.id)
    return {'id':review.id,'actual_paise':actual,'actual_sha256':actual_hash}
