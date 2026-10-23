import hashlib
import math
from datetime import date, timedelta
from pathlib import Path
import pytest
from intelligence import demo_inputs, expense_projection, model_bundle, model_report, score_invoice, simulate
from ml_features import payment_features, sigmoid


def test_artifact_checksum_and_honest_provenance():
    actual=hashlib.sha256((Path(__file__).parent/'models/intelligence.json').read_bytes()).hexdigest()
    assert actual==model_report()['artifact_sha256']
    assert model_bundle()['provenance']=='synthetic_only'
    assert model_report()['payment']['metrics']['logistic_calibrated']['brier']<model_report()['payment']['metrics']['base_rate']['brier']


def test_payment_history_is_strictly_as_of_and_explanations_reconstruct_score():
    now=date(2026,10,23)
    inv=demo_inputs(now)[1][0]
    base=payment_features(inv['total_paise'],inv['due_date'],now,inv['history'])
    future=inv['history']+[{'due_date':now,'paid_date':now+timedelta(days=15)}]
    assert payment_features(inv['total_paise'],inv['due_date'],now,future)==base
    risk=score_invoice(inv,now)
    total=risk['base_log_odds']+sum(c['log_odds_contribution'] for c in risk['contributions'])
    assert total==pytest.approx(risk['predicted_log_odds'],abs=3e-6)
    assert sigmoid(total)==pytest.approx(risk['late_probability'],abs=1e-6)
    overdue={**inv,'due_date':now-timedelta(days=1)}
    assert score_invoice(overdue,now)['late_probability'] is None


@pytest.mark.parametrize('days',[7,30,90])
def test_same_scenario_uses_identical_draws_and_quantiles_are_ordered(days):
    now=date(2026,10,23); entries,invoices=demo_inputs(now)
    result=simulate(1500000,entries,invoices,now,days,paths=50)
    assert result['baseline']==result['scenario']
    assert len(result['baseline']['points'])==days
    assert result['expense_method']=='trained_ridge_expenses'
    for p in result['baseline']['points']:
        assert p['p10_paise']<=p['median_paise']<=p['p90_paise']
        assert isinstance(p['median_paise'],int)


def test_scenario_conserves_receipt_amount_and_deferred_obligations():
    now=date(2026,10,23)
    invoice={'id':'i','customer_name':'Test','total_paise':10000,'outstanding_paise':6000,'due_date':now+timedelta(days=1),'history':[]}
    entry={'id':'e','entry_date':now+timedelta(days=2),'direction':'out','status':'planned','amount_paise':4000,'description':'Total expense'}
    r=simulate(0,[entry],[invoice],now,7,{'i':now},{'e':now+timedelta(days=10)},paths=50)
    assert r['scenario']['closing_median_paise']==6000
    assert r['scenario']['deferred_beyond_horizon_paise']==4000
    assert r['scenario']['points'][0]['median_paise']==6000
    assert r['expense_method']=='no_expense_history'


def test_partial_receipts_not_double_counted_and_disputes_excluded():
    now=date(2026,10,23)
    inv={'id':'i','customer_name':'Test','total_paise':10000,'outstanding_paise':3000,'due_date':now,'history':[],'disputed':True}
    r=simulate(0,[],[inv],now,7,{'i':now},paths=50)
    assert r['baseline']['closing_median_paise']==0
    assert r['scenario']['closing_median_paise']==3000


def test_foreign_scenario_ids_are_rejected():
    with pytest.raises(ValueError): simulate(0,[],[],date(2026,10,23),30,{'foreign':date(2026,10,24)},paths=50)


def test_future_actual_expenses_never_leak_into_forecast():
    now=date(2026,10,23); entries,_=demo_inputs(now)
    expected=expense_projection(entries,now,7)
    future={'id':'f','entry_date':now+timedelta(days=1),'direction':'out','status':'actual','amount_paise':999999999,'description':'Future'}
    assert expense_projection(entries+[future],now,7)==expected
