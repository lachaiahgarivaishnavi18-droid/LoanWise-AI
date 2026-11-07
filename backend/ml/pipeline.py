import json
from pathlib import Path
from datetime import datetime, timezone
from functools import lru_cache
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, average_precision_score, confusion_matrix, brier_score_loss
from sklearn.calibration import calibration_curve
from app.config import settings

FEATURES = ['dti', 'lti', 'employment_months', 'credit_utilization', 'missed_payments']
LIMITATIONS = ['Trained only on synthetic data; no real-world predictive validity.', 'The uncalibrated score describes model behavior, not an individual default probability.', 'SHAP contributions explain model behavior, not causation or a legal decision.', 'Fairness across demographic groups is unmeasured; no demographic data is collected.']


def synthetic_training(n=1600):
    rng = np.random.default_rng(42)
    x = pd.DataFrame({'dti': rng.uniform(3, 85, n), 'lti': rng.uniform(.1, 8, n), 'employment_months': rng.integers(0, 180, n), 'credit_utilization': rng.uniform(0, 100, n), 'missed_payments': rng.poisson(.7, n)})
    logit = -4 + x.dti * .045 + x.lti * .14 - x.employment_months * .006 + x.credit_utilization * .014 + x.missed_payments * .5
    y = rng.binomial(1, 1 / (1 + np.exp(-logit)))
    return x, y


def metrics(y, p):
    pred = p >= .5
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    observed, predicted = calibration_curve(y, p, n_bins=8)
    return {'accuracy': accuracy_score(y, pred), 'precision': precision_score(y, pred, zero_division=0), 'recall': recall_score(y, pred, zero_division=0), 'f1': f1_score(y, pred, zero_division=0), 'roc_auc': roc_auc_score(y, p), 'pr_auc': average_precision_score(y, p), 'specificity': float(tn / max(tn + fp, 1)), 'brier_score': brier_score_loss(y, p), 'confusion_matrix': [[int(tn), int(fp)], [int(fn), int(tp)]], 'calibration': {'predicted': predicted.tolist(), 'observed': observed.tolist()}}


def train():
    from xgboost import XGBClassifier
    directory = Path(settings.model_dir)
    directory.mkdir(parents=True, exist_ok=True)
    x, y = synthetic_training()
    x_train, x_other, y_train, y_other = train_test_split(x, y, test_size=.4, random_state=42, stratify=y)
    x_val, x_test, y_val, y_test = train_test_split(x_other, y_other, test_size=.5, random_state=42, stratify=y_other)
    estimators = {'Logistic Regression': make_pipeline(SimpleImputer(), StandardScaler(), LogisticRegression(random_state=42)), 'Decision Tree': DecisionTreeClassifier(max_depth=4, random_state=42), 'Random Forest': RandomForestClassifier(n_estimators=120, max_depth=6, min_samples_leaf=8, random_state=42, n_jobs=-1), 'Gradient Boosting': GradientBoostingClassifier(n_estimators=80, max_depth=2, random_state=42), 'XGBoost': XGBClassifier(n_estimators=80, max_depth=2, learning_rate=.06, random_state=42, n_jobs=2)}
    estimators = {name: estimator if name == 'Logistic Regression' else make_pipeline(SimpleImputer(), estimator) for name, estimator in estimators.items()}
    evaluation = {}
    for name, model in estimators.items():
        model.fit(x_train, y_train)
        evaluation[name] = {'validation': metrics(y_val, model.predict_proba(x_val)[:, 1]), 'test': metrics(y_test, model.predict_proba(x_test)[:, 1])}
    # Logistic baseline gives exact, stable log-odds SHAP. Compare models without test-set selection.
    selected = 'Logistic Regression'
    model = estimators[selected]
    import shap
    transformed = model[:-1].transform(x_train)
    explainer = shap.LinearExplainer(model[-1], transformed)
    values = explainer(model[:-1].transform(x_test)).values
    run_version = 'synthetic-v2-' + joblib.hash({'models': estimators, 'features': FEATURES, 'data': (x, y)})[:12]
    report = {'synthetic': True, 'version': run_version, 'selected_model': selected, 'selection_reason': 'Interpretable logistic baseline chosen a priori; validation/test metrics are comparisons, not proof of lending performance.', 'split': {'train': len(x_train), 'validation': len(x_val), 'test': len(x_test), 'seed': 42, 'strategy': 'stratified independent synthetic records; no temporal observations'}, 'positive_fraction': float(y.mean()), 'models': evaluation, 'global_importance': [{'feature': f, 'mean_absolute_shap': float(v)} for f, v in zip(FEATURES, np.abs(values).mean(axis=0))], 'limitations': LIMITATIONS}
    q1=x_train.quantile(.25); q3=x_train.quantile(.75); spread=q3-q1
    report['data_diagnostics']={'feature_allowlist':FEATURES,'training_missing_counts':x_train.isna().sum().to_dict(),'training_iqr_outlier_counts':((x_train<q1-1.5*spread)|(x_train>q3+1.5*spread)).sum().to_dict(),'split_disjoint':bool(set(x_train.index).isdisjoint(x_val.index) and set(x_train.index).isdisjoint(x_test.index) and set(x_val.index).isdisjoint(x_test.index)),'feature_selection':'Documented five-feature allowlist; no test-set-driven selection or automatic outlier deletion.'}
    groups=np.random.default_rng(43).choice(['SYNTHETIC_COHORT_A','SYNTHETIC_COHORT_B'],len(y_test))
    report['synthetic_fairness']=fairness_metrics(y_test,model.predict_proba(x_test)[:,1]>=.5,groups)
    report['synthetic_fairness']['governance']='Random synthetic cohorts only; not demographics or real-world fairness evidence.'
    for name, estimator in estimators.items():
        joblib.dump(estimator,directory/f"{name.lower().replace(' ','-')}-{run_version}.joblib")
    artifact={'model':model,'explainer':explainer,'report':report}
    joblib.dump(artifact,directory/f'credit-{run_version}.joblib')
    temporary=directory/'credit.pending.joblib'
    joblib.dump(artifact,temporary)
    temporary.replace(directory/'credit.joblib')
    (directory / 'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    out = Path(settings.data_dir, 'synthetic'); out.mkdir(parents=True, exist_ok=True)
    x.assign(synthetic_label=y, synthetic=True).to_csv(out / 'training.csv', index=False)
    from app.database import SessionLocal
    from app.normalized_services import persist_model_evaluation
    with SessionLocal() as db:
        persist_model_evaluation(db, report)
        db.commit()
    load_model.cache_clear()
    return report


@lru_cache(maxsize=1)
def load_model():
    path = Path(settings.model_dir) / 'credit.joblib'
    return joblib.load(path) if path.exists() else None


def predict(application, features,allowed_features=None):
    p = application.profile
    values = {f: features.get(f) if f in features else p.get(f) for f in FEATURES}
    restricted=[feature for feature in FEATURES if allowed_features is not None and feature not in allowed_features]
    for feature in restricted:
        values[feature]=None
    if not p.get('credit_verified'):
        values['credit_utilization'] = values['missed_payments'] = None
    missing = [f for f, v in values.items() if v is None]
    artifact = load_model()
    base = {'model_name': 'Logistic Regression', 'version': artifact['report']['version'] if artifact else 'untrained-synthetic', 'synthetic_model': True, 'features': values, 'missing_features': missing, 'limitations': LIMITATIONS, 'timestamp': datetime.now(timezone.utc).isoformat(), 'score': None, 'category': 'INSUFFICIENT INFORMATION', 'contributions': []}
    base['restricted_features']=restricted
    if restricted:
        base['limitations']=LIMITATIONS+['Configured jurisdiction feature policy excludes: '+', '.join(restricted)+'. No model estimate was produced.']
    if missing or artifact is None:
        base['limitations'] = base['limitations'] + (['Run python -m ml.pipeline to train the demo model.'] if artifact is None else [])
        return base
    frame = pd.DataFrame([values], columns=FEATURES)
    model = artifact['model']
    score = float(model.predict_proba(frame)[0, 1])
    transformed = model[:-1].transform(frame)
    explanation = artifact['explainer'](transformed)
    base.update(score=score, category='LOW RISK' if score < settings.risk_low_threshold else 'MODERATE RISK' if score < settings.risk_high_threshold else 'HIGHER RISK', thresholds={'low_below': settings.risk_low_threshold, 'higher_at': settings.risk_high_threshold, 'scope': 'synthetic demonstration only'}, baseline=float(explanation.base_values[0]), explanation_units='log-odds', contributions=[{'feature': f, 'value': values[f], 'contribution': float(v), 'direction': 'raises model score' if v > 0 else 'lowers model score'} for f, v in zip(FEATURES, explanation.values[0])])
    return base


def fairness_metrics(y, prediction, groups):
    """Diagnostic helper for separately governed lawful datasets. Never infers demographics."""
    result = {}
    for group in np.unique(groups):
        mask = np.asarray(groups) == group
        tn, fp, fn, tp = confusion_matrix(np.asarray(y)[mask], np.asarray(prediction)[mask], labels=[0, 1]).ravel()
        result[str(group)] = {'selection_rate': float(np.mean(np.asarray(prediction)[mask])), 'tpr': float(tp / (tp + fn)) if tp + fn else None, 'fpr': float(fp / (fp + tn)) if fp + tn else None, 'fnr': float(fn / (fn + tp)) if fn + tp else None}
    def difference(key):
        vals = [v[key] for v in result.values() if v[key] is not None]
        return max(vals) - min(vals) if len(vals) > 1 else None
    return {'groups': result, 'demographic_parity_difference': difference('selection_rate'), 'equal_opportunity_difference': difference('tpr'), 'equalized_odds_difference': max(difference('tpr') or 0, difference('fpr') or 0), 'limitations': 'Diagnostic only; not legal compliance evidence.'}


if __name__ == '__main__':
    print(json.dumps(train(), indent=2))
