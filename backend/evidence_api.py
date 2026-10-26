from fastapi import APIRouter,Response,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from audit import record_event
from evidence import invoice_packet,make_bundle
from operations_api import authorize,mutation
from request_limits import allow_action
from saas_api import Identity,Db

router=APIRouter(prefix='/api/v1/organizations/{organization_id}/evidence',tags=['private-evidence-export'])
class ExportInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirmed_private_download:bool=Field(default=False,strict=True)


@router.post('/invoices/{invoice_id}/preview')
def preview_export(organization_id:str,invoice_id:str,identity:Identity,db:Db):
    authorize(db,identity,organization_id,admin=True)
    try:
        packet=invoice_packet(db,organization_id,invoice_id,identity)
        return {'invoice_number':packet['invoice.json']['invoice']['invoice_number'],'categories':{
            'documents':len(packet['documents.json']),'receipts':len(packet['ledger.json']['payments']),'memos':len(packet['ledger.json']['memos']),
            'refunds':len(packet['ledger.json']['refunds']),'issues':len(packet['issues.json']),'commitments':len(packet['commitments.json']),
            'completed_contacts':len(packet['contacts.json']['completed_external_contacts']),'consent_changes':len(packet['contacts.json']['customer_consent_history']),
            'reconciliation_matches':len(packet['reconciliation.json']['matches']),'activity_events':len(packet['activity.json'])},
            'note':'Private current application records, including internal notes. Original delivery documents and independently verified provider confirmations are not attached.'}
    except ValueError as e:raise HTTPException(422,str(e))


@router.post('/invoices/{invoice_id}/bundle')
def download_export(organization_id:str,invoice_id:str,payload:ExportInput,identity:Identity,db:Db):
    authorize(db,identity,organization_id,admin=True)
    if not payload.confirmed_private_download:raise HTTPException(422,'Confirm that you intend to download these private records')
    allow_action(identity,'invoice-evidence:'+organization_id,'invoice evidence exports')
    with mutation(db):
        packet=invoice_packet(db,organization_id,invoice_id,identity);content=make_bundle(packet,organization_id,invoice_id)
        record_event(db,organization_id,identity,'invoice.evidence_exported',invoice_id)
    return Response(content,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="cashpilot-invoice-records.zip"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
