from datetime import timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from auth_identity import get_verified_identity
from cash_ledger import CashEntry
from forecast_journal import ForecastSnapshot,create_snapshot,evaluate_snapshot
from forecast_journal_api import router
from intelligence import expense_projection
from intelligence_api import today
from saas_api import get_saas_session
from saas_domain import SaaSBase,Organization,Membership


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr('request_limits._requests',{})
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);SaaSBase.metadata.create_all(engine)
    with Session(engine) as db:
        for org,user in [('a','owner'),('b','bob')]:db.add(Organization(id=org,name=org,mode='b2b'));db.flush();db.add(Membership(organization_id=org,user_id=user,role='owner'))
        db.add(Membership(organization_id='a',user_id='viewer',role='viewer'))
        for days in range(1,101):db.add(CashEntry(organization_id='a',entry_date=today()-timedelta(days=days),direction='out',status='actual',amount_paise=10000,description='Synthetic history'))
        db.commit()
    app=FastAPI();app.include_router(router);who={'id':'owner'};app.dependency_overrides[get_verified_identity]=lambda:who['id']
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_saas_session]=session
    with TestClient(app) as c:yield c,who,engine
    engine.dispose()


BASE='/api/v1/organizations/a/forecast-journal'


def test_saved_forecasts_are_immutable_replay_safe_and_tenant_scoped(api):
    c,who,engine=api
    first=c.post(BASE,json={'request_key':'snapshot-1'});assert first.status_code==201,first.text
    row=first.json();assert row['payload']['expense_method']=='trained_ridge_expenses';assert row['payload']['provenance']=='synthetic_only';assert row['payload']['cash_baseline'] is None
    assert c.post(BASE,json={'request_key':'snapshot-1'}).json()['id']==row['id']
    assert c.post(BASE,json={'request_key':'snapshot-1','opening_paise':100}).status_code==422
    with Session(engine) as db:
        for entry in db.scalars(select(CashEntry)):entry.amount_paise=1
        db.commit();assert db.scalar(select(func.count()).select_from(ForecastSnapshot))==1
    detail=c.get(BASE+'/'+row['id']).json();assert detail['payload']==row['payload'];assert all(not e['closed'] and e['recorded_actual_paise'] is None for e in detail['evaluation'])
    assert c.post(BASE+'/'+row['id']+'/reviews',json={'horizon_days':7,'note':'Too early','confirmed_complete':True}).status_code==422
    who['id']='viewer';assert c.get(BASE+'/'+row['id']).status_code==200;assert c.post(BASE,json={'request_key':'forbidden'}).status_code==403
    who['id']='bob';assert c.get(BASE+'/'+row['id']).status_code==403


def test_actual_review_waits_for_closed_window_and_becomes_stale_after_edits(api):
    c,who,engine=api
    with Session(engine) as db:
        # Only the local fixture can create a historical origin; the public API
        # always snapshots today and cannot backdate a forecast after seeing data.
        row=create_snapshot(db,'a','owner',today()-timedelta(days=8),'historical-fixture');db.commit();sid=row.id
        original=row.payload['expense_totals']['7']
    detail=c.get(BASE+'/'+sid).json();seven=detail['evaluation'][0];assert seven['closed'] is True and seven['recorded_actual_paise']==70000;assert seven['coverage_confirmed'] is False and seven['absolute_percentage_error'] is None
    response=c.post(BASE+'/'+sid+'/reviews',json={'horizon_days':7,'note':'Synthetic fixture complete records reviewed','confirmed_complete':True});assert response.status_code==201
    reviewed=c.get(BASE+'/'+sid).json()['evaluation'][0];assert reviewed['coverage_confirmed'] is True;assert reviewed['absolute_percentage_error']==round(abs(original-70000)/70000*100,2)
    with Session(engine) as db:
        entry=db.scalar(select(CashEntry).where(CashEntry.entry_date==today()-timedelta(days=4)));entry.amount_paise+=1000;db.commit()
    stale=c.get(BASE+'/'+sid).json()['evaluation'][0];assert stale['review_stale'] is True and stale['coverage_confirmed'] is False and stale['absolute_percentage_error'] is None


def test_optional_cash_attention_is_conditional_on_supplied_opening(api):
    c,who,engine=api
    row=c.post(BASE,json={'request_key':'conditional','opening_paise':0,'threshold_paise':1000}).json()
    assert row['payload']['attention'][0]['code']=='conditional_cash_threshold';assert len(row['payload']['cash_baseline']['points'])==90


def test_expenses_outside_the_recent_window_do_not_qualify_model_history():
    entries=[{'entry_date':today()-timedelta(days=500+i),'direction':'out','status':'actual','amount_paise':100} for i in range(30)]
    entries.append({'entry_date':today()-timedelta(days=2),'direction':'out','status':'actual','amount_paise':100})
    assert expense_projection(entries,today(),7)[2]=='trailing_mean_insufficient_history'
