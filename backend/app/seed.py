import json
import random
import secrets
from pathlib import Path
from sqlalchemy import select
from .models import User, Applicant, Product, Application, Document
from .security import hash_password
from ai.documents import index_document
from .config import settings


def seed(db):
    from .normalized_services import initialize_roles
    initialize_roles(db)
    if db.scalar(select(User).limit(1)):
        return
    password = secrets.token_urlsafe(18)
    user = User(email='demo@loanwise.local', name='Alex Morgan', role='admin', password_hash=hash_password(password))
    db.add(user); db.flush()
    Path(settings.runtime_dir).mkdir(parents=True, exist_ok=True)
    # Local generated credential is never committed or returned by an unauthenticated API.
    Path(settings.runtime_dir, 'demo-credentials.txt').write_text(f'Email: {user.email}\nPassword: {password}\n', encoding='utf-8')
    products = []
    for name, income, max_dti, max_amount, months in [('Personal Flex', 25000, 45, 1500000, 60), ('Home Advantage', 40000, 50, 10000000, 360), ('Business Growth', 60000, 40, 5000000, 120)]:
        product = Product(name=name, description=f'Synthetic {name.lower()} lending product. Not a real offer.', policy_version='DEMO-2026.1', criteria=[])
        db.add(product); db.flush()
        specifications = [('monthly_income', 'Minimum verified monthly income', 'min', income), ('dti', 'Maximum debt-to-income ratio (%)', 'max', max_dti), ('amount', 'Maximum requested principal', 'max', max_amount), ('tenure_months', 'Maximum tenure in months', 'max', months), ('employment_months', 'Minimum employment duration in months', 'min', 12)]
        lines = [f'{label}: {threshold}. Operator: {operator}.' for key, label, operator, threshold in specifications]
        content = f'SYNTHETIC DEMONSTRATION POLICY — {name}\nVersion DEMO-2026.1. Effective 2026-01-01. Currency INR.\n' + '\n'.join(lines) + '\nAll assessments require authorized human review. These invented demo thresholds are not bank rules or legal guidance.'
        doc = Document(owner_id=user.id, title=f'{name} · Demo lending policy', kind='policy', path='', version='DEMO-2026.1', effective_date='2026-01-01', product_id=product.id, pages=[{'page': 1, 'text': content}], extraction={'entities': [], 'warnings': [], 'quarantined': False}, reviewed=True, synthetic=True)
        db.add(doc); db.flush(); index_document(db, doc)
        product.criteria = [dict(key=key, label=label, operator=op, threshold=threshold, document_id=doc.id, page=1, quote=line) for (key, label, op, threshold), line in zip(specifications, lines)]
        products.append(product)
        path = Path(settings.data_dir, 'sample_policies'); path.mkdir(parents=True, exist_ok=True)
        (path / f'{product.id}.txt').write_text(content, encoding='utf-8')
    rng = random.Random(42)
    exported = []
    for i in range(500):
        applicant = Applicant(owner_id=user.id, name=f'Demo Applicant {i + 1:03}', reference=f'SYN-{i + 1:05}', synthetic=True)
        db.add(applicant); db.flush()
        income = rng.randrange(20000, 180000, 1000)
        profile = {'monthly_income': income if i % 17 else None, 'monthly_debt': rng.randrange(1000, 55000, 500), 'monthly_expenses': rng.randrange(8000, 25000, 500), 'employment_months': rng.randrange(3, 160), 'credit_score': None if i % 13 == 0 else rng.randrange(540, 860), 'credit_utilization': rng.randrange(5, 95), 'missed_payments': rng.choice([0, 0, 0, 1, 2, 4]), 'income_verified': i % 17 != 0, 'credit_verified': i % 13 != 0, 'income_conflict': i % 29 == 0}
        product = products[i % 3]
        application = Application(applicant_id=applicant.id, product_id=product.id, amount=rng.randrange(2, 30) * 100000, tenure_months=[36, 240, 84][i % 3], annual_rate=[12, 8.5, 14][i % 3], profile=profile, synthetic=True)
        db.add(application); db.flush()
        from .normalized_models import RepaymentRecord
        for collection in ['incomes','expenses','liabilities','employment','credit_accounts']:
            for record in getattr(application.profile_record,collection):
                record.source_type='SYNTHETIC_GENERATOR'
        history_rng=random.Random(1000+i)
        missed=set(history_rng.sample(range(12),min(profile['missed_payments'] or 0,12)))
        application.profile_record.credit_accounts[0].repayments=[RepaymentRecord(period=f'2025-{month+1:02}',status='MISSED' if month in missed else 'PAID') for month in range(12)]
        text = f'SYNTHETIC INCOME RECORD\nApplicant: {applicant.reference}\nMonthly income: {income + (10000 if profile["income_conflict"] else 0)}\nMonthly debt: {profile["monthly_debt"]}\nThis is not a real financial document.'
        doc = Document(owner_id=user.id, application_id=application.id, title=f'{applicant.reference} income record', kind='financial', path='', version='1', pages=[{'page': 1, 'text': text}], extraction={'entities': [{'field': 'monthly income', 'value': income, 'page': 1, 'quote': f'Monthly income: {income}', 'verified': False}], 'warnings': ['Synthetic extraction example; manual review required.'], 'quarantined': False}, reviewed=False, synthetic=True)
        db.add(doc)
        exported.append({'reference': applicant.reference, 'profile': profile, 'amount': application.amount, 'synthetic': True})
    folder = Path(settings.data_dir, 'synthetic'); folder.mkdir(parents=True, exist_ok=True)
    (folder / 'applicants.json').write_text(json.dumps(exported, indent=2), encoding='utf-8')
    from ml.demo_data import export_details
    export_details(exported, folder)
    db.commit()
