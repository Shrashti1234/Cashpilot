from pathlib import Path

from test_financial_approvals import api
from banking_api import router as banking
from business_clock import india_today
from collection_worklist_api import router as worklist
from receivable_import_api import router as imports

FIXTURES = Path(__file__).resolve().parents[1] / 'examples' / 'pilot'


def test_import_receipt_and_bank_match_without_payment_provider(api):
    client, _, _ = api
    for router in (banking, worklist, imports):
        client.app.include_router(router)
    base = '/api/v1/organizations/a'
    importer = base + '/receivable-import'
    data = {
        'content': (FIXTURES / 'open-receivables.csv').read_text(encoding='utf-8'),
        'columns': {name: name for name in ('customer', 'reference', 'due', 'amount')},
    }
    preview = client.post(importer + '/preview', json=data)
    assert preview.status_code == 200
    digest = preview.json()['preview_digest']
    assert client.post(importer + '/commit', json={**data, 'preview_digest': digest}).json()['imported'] == 1
    tasks = base + '/collections/worklist'
    row = client.get(tasks, params={'q': 'PILOT-100'}).json()['actions'][0]
    assert row['outstanding_paise'] == 100000
    invoice = row['invoice_id']
    day = str(india_today())
    assert client.post(tasks + '/' + invoice, json={'assignee': 'owner', 'follow_up': day}).status_code == 200
    payments = f'{base}/invoices/{invoice}/payments'
    payment = {'amount_paise': 100000, 'idempotency_key': 'pilot-receipt'}
    receipt = client.post(payments, json=payment)
    assert receipt.status_code == 201
    assert client.post(payments, json=payment).json()['id'] == receipt.json()['id']
    assert client.get(tasks, params={'q': 'PILOT-100'}).json()['total'] == 0

    bank = base + '/banking'
    account = client.post(bank + '/accounts', json={'label': 'Pilot bank'}).json()['id']
    statement = f'{bank}/accounts/{account}'
    data = {'csv_text': (FIXTURES / 'bank-statement.csv').read_text(encoding='utf-8')}
    assert client.post(statement + '/import', json=data).json()['imported'] == 1
    transaction = client.get(statement + '/transactions').json()['rows'][0]
    match = f"{bank}/transactions/{transaction['id']}"
    [candidate] = client.get(match + '/candidates').json()['candidates']
    assert candidate['label'] == 'Receipt · PILOT-100 · Pilot Buyer'
    assert candidate['id'] == receipt.json()['id']
    response = client.post(match + '/match', json={'kind': 'payment', 'target_id': candidate['id'], 'note': 'Verified sample transfer', 'confirmed': True})
    assert response.status_code == 201
    assert client.get(statement + '/transactions').json()['summary']['matched_count'] == 1
    assert len(client.get(payments).json()['payments']) == 1
