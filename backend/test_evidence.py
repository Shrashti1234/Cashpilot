from io import BytesIO
import hashlib
import json
from zipfile import ZipFile,ZIP_DEFLATED
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from test_buyer_api import api
from audit import AuditEvent
from evidence_api import router
from verify_evidence import verify_bundle

BASE='/api/v1/organizations/a/evidence/invoices/ia'


def test_invoice_bundle_is_scoped_complete_checksummed_and_excludes_private_codes(api,tmp_path):
    c,who,engine=api;c.app.include_router(router)
    link=c.post('/api/v1/organizations/a/buyer-access',json={'invoice_id':'ia'}).json()
    preview=c.post(BASE+'/preview');assert preview.status_code==200;assert preview.json()['categories']['memos']==1
    assert c.post(BASE+'/bundle',json={'confirmed_private_download':False}).status_code==422
    response=c.post(BASE+'/bundle',json={'confirmed_private_download':True});assert response.status_code==200,response.text;assert response.headers['content-type']=='application/zip';assert response.headers['cache-control']=='no-store'
    with ZipFile(BytesIO(response.content)) as archive:
        manifest=json.loads(archive.read('manifest.json'));assert manifest['invoice_id']=='ia' and manifest['organization_id']=='a'
        for name,info in manifest['files'].items():assert hashlib.sha256(archive.read(name)).hexdigest()==info['sha256'];assert len(archive.read(name))==info['bytes']
        combined='\n'.join(archive.read(name).decode() for name in archive.namelist())
        assert 'SENSITIVE_INTERNAL_STRATEGY' in combined
        assert all(value not in combined for value in ['SECRET-1','Secret foreign',link['token'],hashlib.sha256(link['token'].encode()).hexdigest(),'"token_hash"','"request_key"','"idempotency_key"'])
        ledger=json.loads(archive.read('ledger.json'));assert ledger['outstanding_paise']==9000
        assert json.loads(archive.read('documents.json'))==[]
    path=tmp_path/'bundle.zip';path.write_bytes(response.content);assert verify_bundle(path)==9
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action=='invoice.evidence_exported'))==1


def test_bundle_controls_require_admin_and_never_expose_other_business(api):
    c,who,engine=api;c.app.include_router(router)
    who['id']='viewer';assert c.post(BASE+'/preview').status_code==403;assert c.post(BASE+'/bundle',json={'confirmed_private_download':True}).status_code==403
    who['id']='bob';assert c.post(BASE+'/bundle',json={'confirmed_private_download':True}).status_code==403
    who['id']='owner';assert c.post('/api/v1/organizations/a/evidence/invoices/ib/bundle',json={'confirmed_private_download':True}).status_code==422


def test_offline_verifier_rejects_changed_records_without_extracting(api,tmp_path):
    c,who,engine=api;c.app.include_router(router);original=c.post(BASE+'/bundle',json={'confirmed_private_download':True}).content
    tampered=tmp_path/'tampered.zip'
    with ZipFile(BytesIO(original)) as source,ZipFile(tampered,'w',compression=ZIP_DEFLATED) as target:
        for name in source.namelist():target.writestr(name,b'{}' if name=='ledger.json' else source.read(name))
    with pytest.raises(ValueError,match='Checksum'):verify_bundle(tampered)
