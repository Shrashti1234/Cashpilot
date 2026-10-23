"""Explainable, JSON-only model inference and paired cash scenario simulation.

No sklearn/pickle dependency in the serving container. Money stays integer paise.
Uncertainty is conditional on synthetic residual/delay assumptions, never a
calibrated real-world claim. No scenario writes or sends financial actions.
"""
import json
import math
import random
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from ml_features import flow_features, linear_predict, payment_features, sigmoid


@lru_cache(maxsize=1)
def model_bundle():
    return json.loads((Path(__file__).parent / 'models/intelligence.json').read_text(encoding='utf-8'))


def model_report():
    return json.loads((Path(__file__).parent / 'models/evaluation.json').read_text(encoding='utf-8'))


def score_invoice(invoice, as_of):
    model=model_bundle()['payment']
    values=payment_features(invoice['total_paise'],invoice['due_date'],as_of,invoice.get('history',[]))
    raw=linear_predict(model,values)
    log_odds=model['calibration_intercept']+model['calibration_slope']*raw
    base=model['calibration_intercept']+model['calibration_slope']*model['intercept']
    contributions=[{'feature':name,'value':round(value,4),'log_odds_contribution':round(model['calibration_slope']*coef*(value-mean)/scale,6)}
                   for name,value,coef,mean,scale in zip(model['features'],values,model['coefficients'],model['means'],model['scales'],strict=True)]
    overdue=invoice['due_date']<as_of
    outside=[name for name,value,low,high in zip(model['features'],values,model['training_support']['min'],model['training_support']['max'],strict=True) if not low<=value<=high]
    return {'invoice_id':invoice['id'],'customer_name':invoice['customer_name'],'due_date':str(invoice['due_date']),
            'outstanding_paise':invoice['outstanding_paise'],'days_overdue':max(0,(as_of-invoice['due_date']).days),
            'status':'already_overdue' if overdue else 'experimental_prediction',
            'late_probability':None if overdue else round(sigmoid(log_odds),6),
            'simulation_late_probability':1.0 if overdue else sigmoid(log_odds),
            'base_log_odds':base,'predicted_log_odds':log_odds,'contributions':contributions,
            'history_count':int(values[1]),'outside_training_support':outside,
            'disputed':invoice.get('disputed',False)}


def expense_projection(entries,as_of,days):
    actual=[e for e in entries if e['status']=='actual' and e['direction']=='out' and e['entry_date']<as_of]
    if not actual:
        return [0]*days,[0.0]*days,'no_expense_history',0
    first=max(min(e['entry_date'] for e in actual),as_of-timedelta(days=365))
    observed_days=(as_of-first).days
    daily={}
    for entry in actual:
        daily[entry['entry_date']]=daily.get(entry['entry_date'],0)+entry['amount_paise']
    history=[daily.get(first+timedelta(days=i),0) for i in range(observed_days)]
    model=model_bundle()['cashflow']
    learned=observed_days>=model['minimum_history_days'] and len(daily)>=28
    method='trained_ridge_expenses' if learned else 'trailing_mean_insufficient_history'
    forecast=[]; scales=[]
    for i in range(days):
        scale=max(sum(history[-28:])/max(len(history[-28:]),1),1)
        predicted=max(0,linear_predict(model,flow_features([v/scale for v in history[-28:]],as_of+timedelta(days=i)))*scale) if learned else scale if sum(history)>0 else 0
        forecast.append(round(predicted)); scales.append(scale)
        history.append(predicted)
    return forecast,scales,method,observed_days


def percentile(values,q):
    values=sorted(values)
    pos=(len(values)-1)*q; lo=math.floor(pos); hi=math.ceil(pos)
    return round(values[lo]+(values[hi]-values[lo])*(pos-lo))


def simulate(opening_paise,entries,invoices,as_of,days,receipt_overrides=None,expense_overrides=None,paths=300,seed=1729):
    if not 1<=days<=90 or not 50<=paths<=500:
        raise ValueError('Invalid simulation size')
    receipts=receipt_overrides or {}; expenses=expense_overrides or {}
    ids={i['id'] for i in invoices}
    planned_out={e['id'] for e in entries if e['status']=='planned' and e['direction']=='out' and e['entry_date']>=as_of}
    if not set(receipts)<=ids or not set(expenses)<=planned_out:
        raise ValueError('Scenario references an unavailable invoice or planned expense')
    risks=[score_invoice(i,as_of) for i in invoices]
    forecast,scales,method,history_days=expense_projection(entries,as_of,days)
    model=model_bundle()
    rng=random.Random(seed)
    # Draw once and reuse for baseline/scenario and action comparisons: no
    # apparent improvement caused solely by different random samples.
    draws=[]
    for _ in range(paths):
        delays=[]
        for inv,risk in zip(invoices,risks,strict=True):
            is_late=rng.random()<risk['simulation_late_probability']
            elapsed=max(0,(as_of-inv['due_date']).days)
            support=[d for d in model['payment']['late_delay_days'] if d>elapsed]
            delay=rng.choice(support) if support else elapsed+rng.randint(7,30)
            delays.append((inv['due_date']+timedelta(days=delay)) if is_late else inv['due_date'])
        # Seven-day blocks preserve within-block dependence of sampled errors.
        residuals=[]; source=model['cashflow']['residuals']
        while len(residuals)<days:
            index=rng.randrange(max(1,len(source)-6))
            residuals.extend(source[index:index+7])
        draws.append((delays,residuals[:days]))

    def run(receipt_dates,expense_dates):
        balances=[]; minimums=[]; first_shortfalls=[]
        deferred=0
        for entry in entries:
            if entry['id'] in expense_dates and expense_dates[entry['id']]>=as_of+timedelta(days=days) and entry['entry_date']<as_of+timedelta(days=days):
                deferred+=entry['amount_paise']
        for delay_draw,residual_draw in draws:
            inflow=[0]*days; scheduled=[0]*days; planned_dates=set()
            for inv,receipt_date in zip(invoices,delay_draw,strict=True):
                # Open disputes are not assumed collectible until resolved;
                # an explicit receipt scenario can explore their resolution.
                if inv.get('disputed') and inv['id'] not in receipt_dates:
                    continue
                when=receipt_dates.get(inv['id'],receipt_date)
                offset=(when-as_of).days
                if 0<=offset<days: inflow[offset]+=inv['outstanding_paise']
            for entry in entries:
                if entry['status']!='planned' or entry['entry_date']<as_of: continue
                when=expense_dates.get(entry['id'],entry['entry_date'])
                offset=(when-as_of).days
                if 0<=offset<days:
                    if entry['direction']=='in': inflow[offset]+=entry['amount_paise']
                    else: scheduled[offset]+=entry['amount_paise']; planned_dates.add(offset)
                # Deferring an explicitly planned day's total expenses must
                # leave that original day's model estimate suppressed too.
                original=(entry['entry_date']-as_of).days
                if entry['direction']=='out' and 0<=original<days: planned_dates.add(original)
            balance=opening_paise; curve=[]
            for offset in range(days):
                out=scheduled[offset] if offset in planned_dates else max(0,round(forecast[offset]+scales[offset]*residual_draw[offset]))
                balance+=inflow[offset]-out; curve.append(balance)
            balances.append(curve); minimums.append(min(curve))
            first_shortfalls.append(next((i for i,v in enumerate(curve) if v<0),None))
        points=[]
        for i in range(days):
            vals=[b[i] for b in balances]
            points.append({'date':str(as_of+timedelta(days=i)),'p10_paise':percentile(vals,.10),
                           'median_paise':percentile(vals,.5),'p90_paise':percentile(vals,.90)})
        first=next((p['date'] for p in points if p['median_paise']<0),None)
        return {'points':points,'closing_median_paise':points[-1]['median_paise'],
                'minimum_median_paise':percentile(minimums,.5),
                'shortfall_frequency':sum(m<0 for m in minimums)/paths,
                'first_median_shortfall_date':first,'deferred_beyond_horizon_paise':deferred}

    baseline=run({},{}); scenario=run(receipts,expenses)
    actions=[]
    # Shortlist by exposure before the expensive paired path comparison.
    for inv in sorted(invoices,key=lambda x:x['outstanding_paise'],reverse=True)[:5]:
        if inv.get('disputed'): continue
        action=run({inv['id']:as_of+timedelta(days=1)},{})
        if action['minimum_median_paise']<=baseline['minimum_median_paise'] and action['shortfall_frequency']>=baseline['shortfall_frequency']:
            continue
        actions.append({'invoice_id':inv['id'],'customer_name':inv['customer_name'],
                        'assumed_receipt_date':str(as_of+timedelta(days=1)),
                        'minimum_balance_improvement_paise':action['minimum_median_paise']-baseline['minimum_median_paise'],
                        'shortfall_frequency_reduction':baseline['shortfall_frequency']-action['shortfall_frequency']})
    actions.sort(key=lambda x:(x['shortfall_frequency_reduction'],x['minimum_balance_improvement_paise']),reverse=True)
    warnings=['Models were trained only on synthetic data; not validated financial advice or a credit score.',
              'Simulation frequencies and 10–90% bands describe these assumptions, not calibrated real-world probabilities.',
              'Future non-invoice income is included only when explicitly planned. Missing historical expense days are treated as zero.',
              'Planned outflows replace the total operating-expense estimate for their original and rescheduled dates; deferral is not a saving.',
              'Invoices are assumed eventually paid; no default-risk model. Open disputes are excluded from baseline receipts.',
              'Receipt dates in scenarios are assumed outcomes, not promised effects of collection activity.']
    if method!='trained_ridge_expenses': warnings.append('Insufficient expense history: no learned expense forecast is used. Add 56 calendar days with at least 28 recorded expense days.')
    if any(r['outside_training_support'] for r in risks): warnings.append('Some invoice inputs lie outside synthetic training support; their model estimates are especially unreliable.')
    return {'as_of':str(as_of),'horizon_days':days,'paths':paths,'seed':seed,'currency':'INR',
            'model_version':model['version'],'training_provenance':model['provenance'],
            'expense_method':method,'expense_history_days':history_days,'baseline':baseline,'scenario':scenario,
            'improvement_paise':scenario['minimum_median_paise']-baseline['minimum_median_paise'],
            'invoice_risks':risks,'recommended_reviews':actions,'warnings':warnings}


def demo_inputs(as_of):
    rng=random.Random(42)
    entries=[]
    for i in range(100):
        day=as_of-timedelta(days=100-i)
        expense=round(230000*(1+.30*math.sin(2*math.pi*day.weekday()/7)+.65*(day.day>=26))*math.exp(rng.gauss(0,.10)))
        entries.append({'id':f'history-{i}','entry_date':day,'direction':'out','status':'actual','amount_paise':expense,'description':'Synthetic operating expense'})
    entries.append({'id':'demo-rent','entry_date':as_of+timedelta(days=8),'direction':'out','status':'planned','amount_paise':1800000,'description':'Synthetic rent and payroll day total'})
    invoices=[]
    for i,(name,amount,due,delays) in enumerate([('Aster Studio',4500000,12,[2,12,18,7]),('Northstar Retail',2800000,5,[-2,0,-1,1]),('Harbor Services',3600000,22,[15,22,9,18])]):
        history=[{'due_date':as_of-timedelta(days=150-j*30),'paid_date':as_of-timedelta(days=150-j*30)+timedelta(days=d)} for j,d in enumerate(delays)]
        invoices.append({'id':f'demo-invoice-{i}','customer_name':name,'total_paise':amount,'outstanding_paise':amount,'due_date':as_of+timedelta(days=due),'history':history})
    return entries,invoices
