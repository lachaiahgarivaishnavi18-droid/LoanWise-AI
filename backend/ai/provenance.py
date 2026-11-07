import hashlib
import json
from sqlalchemy import select
from app.models import Product, Document


def input_fingerprint(db, application):
    product = db.get(Product, application.product_id)
    docs = db.scalars(select(Document).where((Document.application_id == application.id) | ((Document.kind == 'policy') & (Document.product_id == product.id))).order_by(Document.id)).all()
    payload = {'applicant_id': application.applicant_id, 'profile': application.profile, 'amount': application.amount, 'tenure_months': application.tenure_months, 'annual_rate': application.annual_rate, 'product_id': product.id, 'version': product.policy_version, 'criteria': product.criteria, 'documents': [{'id': d.id, 'reviewed': d.reviewed, 'pages': d.pages, 'extraction': d.extraction, 'effective_date': d.effective_date, 'version': d.version} for d in docs]}
    payload['policy_version_id']=product.active_version_id
    payload['jurisdiction']=product.jurisdiction
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
