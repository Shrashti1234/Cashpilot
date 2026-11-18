"""Reproducible synthetic-data benchmark. Run from backend: python training/train.py.

Synthetic results are engineering evidence, NOT validation on Indian businesses.
No private business data or third-party AI API is used.
"""
import hashlib
import json
import math
import platform
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, mean_absolute_error, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from ml_features import PAYMENT_FEATURES, FLOW_FEATURES, flow_features, payment_features, sigmoid, linear_predict

SEED = 20261023
ROOT = Path(__file__).resolve().parents[1]


def export_linear(pipeline):
    scaler, model = pipeline.steps[0][1], pipeline.steps[1][1]
    return {"means": scaler.mean_.tolist(), "scales": scaler.scale_.tolist(),
            "coefficients": np.ravel(model.coef_).tolist(), "intercept": float(np.ravel(model.intercept_)[0])}


def payment_data():
    rng = random.Random(SEED)
    rows = []
    start = date(2023, 1, 1)
    for customer in range(240):
        propensity = rng.uniform(-2.8, 1.8)
        history = []
        for i in range(75):
            issued = start + timedelta(days=i * 14 + rng.randrange(7))
            due = issued + timedelta(days=rng.choice([7, 15, 30]))
            score_date = issued + timedelta(days=rng.randrange(max((due-issued).days, 1)))
            amount = int(math.exp(rng.gauss(10, 1.05)) * 100)
            probability = sigmoid(propensity + .45 * (math.log1p(amount/100)-10))
            late = rng.random() < probability
            delay = rng.randint(1, 35) if late else -rng.randint(0, 7)
            paid_date = due + timedelta(days=delay)
            features = payment_features(amount, due, score_date, history)
            rows.append({"score_date": score_date, "paid_date": paid_date, "due_date": due, "x": features, "y": int(late)})
            history.append({"due_date": due, "paid_date": paid_date})
    return rows


def classifier_metrics(y, p):
    p = np.clip(p, 1e-7, 1-1e-7)
    bins = []
    for lo in np.linspace(0, .9, 10):
        mask = (p >= lo) & (p < lo+.100001)
        if mask.sum():
            bins.append({"predicted": float(p[mask].mean()), "observed": float(y[mask].mean()), "count": int(mask.sum())})
    return {"roc_auc": float(roc_auc_score(y,p)), "pr_auc": float(average_precision_score(y,p)),
            "brier": float(brier_score_loss(y,p)), "log_loss": float(log_loss(y,p)),
            "late_prevalence": float(y.mean()), "calibration_bins": bins}


def train_payment():
    rows = payment_data()
    # Purged time splits: no training label resolves after the next evaluation period begins.
    train_end, validation_end = date(2024,10,1), date(2025,4,1)
    train = [r for r in rows if r['paid_date'] < train_end and r['score_date'] < train_end]
    valid = [r for r in rows if train_end <= r['score_date'] < validation_end and r['paid_date'] < validation_end]
    test = [r for r in rows if r['score_date'] >= validation_end]
    def xy(rs): return np.array([r['x'] for r in rs]), np.array([r['y'] for r in rs])
    xt,yt=xy(train); xv,yv=xy(valid); xe,ye=xy(test)
    candidates={}
    for c in [.05, .5, 5]:
        model=make_pipeline(StandardScaler(),LogisticRegression(C=c,max_iter=1000,random_state=SEED))
        model.fit(xt,yt)
        candidates[c]=(brier_score_loss(yv,model.predict_proba(xv)[:,1]),model)
    selected_c=min(candidates,key=lambda c:candidates[c][0])
    model=candidates[selected_c][1]
    boost=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=12,l2_regularization=5,random_state=SEED)
    boost.fit(xt,yt)
    # Sigmoid calibration uses the disjoint validation period; test remains untouched.
    calibrator=LogisticRegression(C=1e6,max_iter=1000)
    calibrator.fit(model.decision_function(xv).reshape(-1,1),yv)
    coef=float(calibrator.coef_[0,0]); intercept=float(calibrator.intercept_[0])
    predicted=np.array([sigmoid(coef*s+intercept) for s in model.decision_function(xe)])
    metrics={"base_rate":classifier_metrics(ye,np.full(len(ye),yt.mean())),
             "logistic_raw":classifier_metrics(ye,model.predict_proba(xe)[:,1]),
             "logistic_calibrated":classifier_metrics(ye,predicted),
             "gradient_boosting_comparator":classifier_metrics(ye,boost.predict_proba(xe)[:,1])}
    artifact=export_linear(model)
    assert np.allclose([linear_predict(artifact,list(row)) for row in xe],model.decision_function(xe),atol=1e-10)
    artifact.update({"features":PAYMENT_FEATURES,"calibration_slope":coef,"calibration_intercept":intercept,
                     "late_delay_days":[(r['paid_date']-r['due_date']).days for r in train if r['y']][::25],
                     "selected_C":selected_c,"training_support":{"min":xt.min(axis=0).tolist(),"max":xt.max(axis=0).tolist()}})
    return artifact,{"counts":{"train":len(train),"validation_calibration":len(valid),"test":len(test)},
                     "train_labels_before":str(train_end),"validation_labels_before":str(validation_end),
                     "test_scores_from":str(validation_end),"metrics":metrics,
                     "selection":"C selected by validation Brier score; calibrated logistic deployed for exact additive explanations. Boosting is a reported comparator, not silently claimed as served."}


def flow_series(seed, days=1100):
    rng=random.Random(seed)
    start=date(2023,1,1)
    level=rng.uniform(1800,12000)
    result=[]
    for i in range(days):
        day=start+timedelta(days=i)
        level=max(300,level*(1+rng.gauss(.00015,.003)))
        value=level*(1+.30*math.sin(2*math.pi*day.weekday()/7)+.65*(day.day>=26))
        value*=math.exp(rng.gauss(0,.10))
        result.append(value)
    return result


def train_flow():
    # Scale-invariant target: next-day cash amount / trailing 28-day mean.
    xs,ys=[],[]
    series=[flow_series(SEED+i) for i in range(32)]
    start=date(2023,1,1)
    for values in series:
        for i in range(28,650):
            scale=max(sum(values[i-28:i])/28,1)
            history=[v/scale for v in values[:i]]
            xs.append(flow_features(history,start+timedelta(days=i)))
            ys.append(values[i]/scale)
    x,y=np.array(xs),np.array(ys)
    candidates=[]
    for alpha in [.1,10,100]:
        m=make_pipeline(StandardScaler(),Ridge(alpha=alpha))
        m.fit(x,y)
        errors=[]
        for values in series:
            for i in range(650,800):
                scale=max(sum(values[i-28:i])/28,1)
                pred=m.predict([flow_features([v/scale for v in values[:i]],start+timedelta(days=i))])[0]*scale
                errors.append(abs(pred-values[i]))
        candidates.append((float(np.mean(errors)),alpha,m))
    _,alpha,model=min(candidates,key=lambda x:x[0])
    residuals=[]
    for values in series:
        for i in range(650,800):
            scale=max(sum(values[i-28:i])/28,1)
            pred=model.predict([flow_features([v/scale for v in values[:i]],start+timedelta(days=i))])[0]*scale
            residuals.append((values[i]-pred)/scale)
    metrics={}
    for horizon in [7,30,90]:
        actual=[]; learned=[]; baseline=[]
        for values in series:
            for origin in [800,910,1010]:
                history=values[:origin].copy(); naive=history.copy(); predictions=[]; seasonal=[]
                for step in range(horizon):
                    scale=max(sum(history[-28:])/28,1)
                    pred=max(0,model.predict([flow_features([v/scale for v in history],start+timedelta(days=origin+step))])[0]*scale)
                    predictions.append(pred); history.append(pred)
                    seasonal.append(naive[-7]); naive.append(naive[-7])
                actual.append(sum(values[origin:origin+horizon])); learned.append(sum(predictions)); baseline.append(sum(seasonal))
        denom=sum(actual)
        metrics[str(horizon)]={"ridge_total_mae_rupees":float(mean_absolute_error(actual,learned)),
                               "seasonal_naive_total_mae_rupees":float(mean_absolute_error(actual,baseline)),
                               "ridge_wape":float(sum(abs(a-b) for a,b in zip(actual,learned))/denom),
                               "seasonal_naive_wape":float(sum(abs(a-b) for a,b in zip(actual,baseline))/denom),"origins":len(actual)}
    artifact=export_linear(model)
    artifact.update({"features":FLOW_FEATURES,"alpha":alpha,"residuals":residuals,"minimum_history_days":56})
    return artifact,{"training_rows":len(y),"validation_days":[650,799],"test_origins":[800,910,1010],
                     "horizon_metrics":metrics,"target":"daily non-invoice income or operating expense, normalized by trailing 28-day mean"}


def main():
    payment,pm=train_payment(); flow,fm=train_flow()
    artifact={"version":"cashpilot-synthetic-v1","seed":SEED,"provenance":"synthetic_only",
              "payment":payment,"cashflow":flow}
    target=ROOT/'models'; target.mkdir(exist_ok=True)
    payload=json.dumps(artifact,sort_keys=True,indent=2)+'\n'
    (target/'intelligence.json').write_text(payload,encoding='utf-8',newline='\n')
    report={"provenance":"synthetic_only","seed":SEED,"python":platform.python_version(),"sklearn":sklearn.__version__,
            "numpy":np.__version__,"artifact_sha256":hashlib.sha256(payload.encode()).hexdigest(),"payment":pm,"cashflow":fm,
            "limitations":["No validation on real Indian MSME data; scores are experimental, not credit scores.",
                           "Synthetic regularity may inflate results; no causal interpretation.",
                           "Monte Carlo bands reflect residual/payment assumptions, not calibrated real-world coverage."]}
    (target/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({"artifact_sha256":report['artifact_sha256'],"payment_metrics":pm['metrics'],"cashflow_metrics":fm['horizon_metrics']},indent=2))


if __name__=='__main__': main()
