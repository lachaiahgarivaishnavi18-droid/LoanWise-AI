from datetime import date
from app.models import Document
import re
from decimal import Decimal
from sqlalchemy import select


def threshold_in_quote(threshold, quote):
    values = re.findall(r'(?<!\w)[+-]?\d[\d,]*(?:\.\d+)?', quote)
    return any(Decimal(value.replace(',', '')) == Decimal(str(threshold)) for value in values)


def evaluate(db, application, product, features):
    if not product.criteria:
        return {'criteria':[],'overall_status':'INSUFFICIENT INFORMATION','human_review_required':True}
    results = []
    for rule in product.criteria:
        key = rule['key']
        value = features.get(key) if key in features else application.profile.get(key)
        if key in ('amount', 'tenure_months'):
            value = getattr(application, key)
        if key=='reviewed_documents':
            documents=db.scalars(select(Document).where(Document.application_id==application.id,Document.kind=='financial',Document.reviewed==True)).all()
            value=sum(not document.extraction.get('quarantined') and any(page['text'].strip() for page in document.pages) for document in documents)
        document = db.get(Document, rule['document_id'])
        page = next((p['text'] for p in document.pages if p['page'] == rule['page']), '') if document else ''
        valid = bool(document and document.source_record and document.source_record.authorized and document.kind == 'policy' and document.reviewed and not document.extraction.get('quarantined') and document.product_id == product.id and document.version == product.policy_version and document.effective_date and document.effective_date <= date.today().isoformat() and rule['quote'] in page and threshold_in_quote(rule['threshold'], rule['quote']))
        if not valid:
            status = 'NEEDS_HUMAN_REVIEW'
        elif key in ('monthly_income', 'dti', 'lti', 'repayment_burden') and application.profile.get('income_conflict'):
            status = 'CONFLICTING'
        elif value is None or (key == 'credit_score' and not application.profile.get('credit_verified')):
            status = 'UNKNOWN'
        else:
            status = 'SATISFIED' if (value >= rule['threshold'] if rule['operator'] == 'min' else value <= rule['threshold']) else 'NOT_SATISFIED'
        results.append({**rule, 'value': value, 'status': status, 'evidence_valid': valid, 'document_title': document.title if document else None, 'policy_version': product.policy_version})
    statuses = {r['status'] for r in results}
    overall = 'ELIGIBILITY CONDITIONS SATISFIED — HUMAN REVIEW REQUIRED'
    for candidate, label in [('NOT_SATISFIED', 'POTENTIAL ELIGIBILITY ISSUES'), ('NEEDS_HUMAN_REVIEW', 'MANUAL REVIEW REQUIRED'), ('UNKNOWN', 'INSUFFICIENT INFORMATION'), ('CONFLICTING', 'CONFLICTING INFORMATION')]:
        if candidate in statuses:
            overall = label
    return {'criteria': results, 'overall_status': overall, 'human_review_required': True}
