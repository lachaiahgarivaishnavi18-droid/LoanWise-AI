from sqlalchemy import select,func,inspect
from app.database import SessionLocal,engine
from app.models import Application,Document,Chunk,Product
from app.normalized_models import IncomeRecord,RepaymentRecord,EligibilityCriterionResult,ModelPrediction,ShapExplanation,RetrievedEvidence,PolicyVersion,GeneratedResponse


def test_canonical_schema_and_synthetic_history(admin):
    inspector=inspect(engine)
    for table,column in [('loan_applications','profile'),('loan_products','criteria'),('financial_documents','pages'),('financial_documents','extraction'),('document_chunks','document_id')]:
        assert column not in {c['name'] for c in inspector.get_columns(table)}
    required={'roles','permissions','applicant_profiles','income_records','expense_records','employment_records','liabilities','credit_accounts','repayment_records','document_pages','extracted_financial_entities','knowledge_sources','policy_documents','policy_versions','eligibility_criteria','eligibility_criterion_results','financial_features','ml_models','model_versions','model_predictions','model_evaluations','shap_explanations','retrieved_evidence','generated_responses','reviewer_comments','fairness_evaluations','application_feedback'}
    assert required.issubset(set(inspector.get_table_names()))
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RepaymentRecord))>=6000
        assert db.get(Application,2).profile_record.credit_accounts[0].repayments


def test_multiple_income_sources_and_zero_debt(admin):
    response=admin.put('/api/applications/20/financial-records',json={'incomes':[{'amount':600000,'frequency':'ANNUAL','verified':True},{'amount':12000,'frequency':'MONTHLY','verified':True}], 'liabilities':[{'monthly_payment':0}], 'employment':[{'duration_months':24}]})
    assert response.status_code==200,response.text
    assert response.json()['profile']['monthly_income']==62000
    assert response.json()['profile']['monthly_debt']==0
    assert admin.get('/api/financial/20').json()['dti']==0
    response=admin.put('/api/applications/20/financial-records',json={'incomes':[],'liabilities':[{'monthly_payment':0}]})
    assert response.status_code==200
    assert response.json()['profile']['monthly_income'] is None
    assert admin.get('/api/financial/20').json()['dti'] is None
    assert admin.put('/api/applications/20/financial-records',json={'incomes':[{'amount':100,'source_type':'DOCUMENT','source_document_id':4}]}).status_code==422


def test_reindex_preserves_historical_citations(admin):
    response=admin.post('/api/rag/query',json={'question':'minimum monthly income','product_id':1})
    assert response.status_code==200
    original=response.json()
    assert original['citations']
    with SessionLocal() as db:
        assert db.scalar(select(GeneratedResponse).where(GeneratedResponse.query_id==original['query_id']))
        assert db.scalar(select(RetrievedEvidence).where(RetrievedEvidence.query_id==original['query_id']))
    assert admin.post('/api/documents/1/review').status_code==200
    with SessionLocal() as db:
        assert all(db.get(Chunk,identifier) is not None for identifier in original['citations'])
        assert all(not db.get(Chunk,identifier).active for identifier in original['citations'])
    historical=admin.get('/api/rag/evidence/'+str(original['query_id']))
    assert historical.status_code==200
    assert historical.json()['answer']==original['answer']


def test_assessment_writes_normalized_results(admin):
    response=admin.post('/api/eligibility/assess',json={'application_id':4})
    assert response.status_code==200,response.text
    identifier=response.json()['assessment_id']
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EligibilityCriterionResult).where(EligibilityCriterionResult.assessment_id==identifier))==5
        assert db.scalar(select(ModelPrediction).where(ModelPrediction.assessment_id==identifier))
    history=admin.get('/api/credit-risk/4/history')
    assert history.status_code==200
    assert history.json()[0]['assessment_id']==identifier
    assert admin.get('/api/assessments/'+str(identifier)).json()['assessment_id']==identifier
    assert admin.get('/api/eligibility/4/history').json()[0]['assessment_id']==identifier


def test_policy_revisions_preserve_previous_criteria(admin):
    product=admin.get('/api/products').json()[0]
    body={key:product[key] for key in ['policy_version','jurisdiction','criteria']}
    body['jurisdiction']='SYNTHETIC DEMO REVISED'
    with SessionLocal() as db:
        previous=db.get(Product,product['id']).active_version_id
    response=admin.put('/api/products/'+str(product['id'])+'/criteria',json=body)
    assert response.status_code==200,response.text
    with SessionLocal() as db:
        assert db.get(Product,product['id']).active_version_id!=previous
        assert db.get(PolicyVersion,previous).jurisdiction!='SYNTHETIC DEMO REVISED'
        assert len(db.get(PolicyVersion,previous).criteria)==5
    result=admin.post('/api/eligibility/assess',json={'application_id':1}).json()
    from app.normalized_models import EligibilityCriterion
    with SessionLocal() as db:
        versions=db.scalars(select(EligibilityCriterion.policy_version_id).join(EligibilityCriterionResult).where(EligibilityCriterionResult.assessment_id==result['assessment_id'])).all()
        assert versions and set(versions)=={result['policy_version_id']}


def test_policy_permissions_restrict_source_and_old_answers(admin):
    from fastapi.testclient import TestClient
    from app.main import app,buckets
    buckets.clear()
    with TestClient(app) as analyst:
        credentials={'email':'policy-access@example.test','password':'long-test-password'}
        analyst.post('/api/auth/register',json=credentials)
        analyst.post('/api/auth/login',json=credentials)
        query=analyst.post('/api/rag/query',json={'question':'minimum income','product_id':1}).json()
        assert query['evidence']
        assert admin.put('/api/documents/1/permissions',json={'roles':['admin']}).status_code==200
        assert analyst.get('/api/documents/1').status_code==404
        assert not analyst.post('/api/rag/query',json={'question':'minimum income','product_id':1}).json()['evidence']
        assert analyst.get('/api/rag/evidence/'+str(query['query_id'])).status_code==404
        assert admin.put('/api/documents/1/permissions',json={'roles':['admin','analyst','reviewer']}).status_code==200


def test_empty_policy_never_satisfies_eligibility(admin):
    product=admin.post('/api/products',json={'name':'Unconfigured synthetic product','description':'Synthetic missing policy fixture','policy_version':'1','jurisdiction':'DEMO'})
    assert product.status_code==201,product.text
    applicant=admin.post('/api/applicants',json={'name':'Synthetic missing-policy applicant'}).json()
    application=admin.post('/api/applications',json={'applicant_id':applicant['id'],'product_id':product.json()['id'],'amount':100000,'tenure_months':12,'annual_rate':0,'profile':{}})
    assert application.status_code==201,application.text
    result=admin.post('/api/eligibility/assess',json={'application_id':application.json()['id']})
    assert result.status_code==200,result.text
    assert result.json()['eligibility']['overall_status']=='INSUFFICIENT INFORMATION'
    assert result.json()['eligibility']['human_review_required']


def test_assistant_uses_only_selected_application_facts(admin):
    response=admin.put('/api/applications/30/financial-records',json={'incomes':[{'amount':50000,'verified':True}],'liabilities':[{'monthly_payment':10000}]})
    assert response.status_code==200
    answer=admin.post('/api/rag/query',json={'question':'What does my DTI ratio indicate?','application_id':30})
    assert answer.status_code==200,answer.text
    assert answer.json()['application_context']['financial']['dti']==20
    assert 'DTI: 20.0 %' in answer.json()['answer']
    assert 'Selected application #30' in answer.json()['answer']
    report=admin.get('/api/reports/retrieval')
    assert report.status_code==200,report.text
    assert len(report.json()['cases'])==9


def test_document_criterion_counts_only_reviewed_sources(admin):
    product=admin.post('/api/products',json={'name':'Synthetic documentation product','description':'Synthetic reviewed-source requirement','policy_version':'1','jurisdiction':'DEMO'}).json()
    quote='Minimum reviewed documents: 1. Operator: min.'
    policy=admin.post('/api/documents/upload',files={'file':('document-policy.txt',quote.encode())},data={'kind':'policy','product_id':product['id'],'version':'1','effective_date':'2026-01-01'})
    assert policy.status_code==201,policy.text
    assert admin.post(f"/api/documents/{policy.json()['id']}/review").status_code==200
    configuration={'policy_version':'1','jurisdiction':'DEMO','criteria':[{'key':'reviewed_documents','label':'Minimum reviewed documents','operator':'min','threshold':1,'document_id':policy.json()['id'],'page':1,'quote':quote}]}
    assert admin.put(f"/api/products/{product['id']}/criteria",json=configuration).status_code==200
    applicant=admin.post('/api/applicants',json={'name':'Synthetic documentation applicant'}).json()
    application=admin.post('/api/applications',json={'applicant_id':applicant['id'],'product_id':product['id'],'amount':100000,'tenure_months':12,'annual_rate':0,'profile':{}}).json()
    identifier=application['id']
    result=admin.post('/api/eligibility/assess',json={'application_id':identifier}).json()
    assert result['eligibility']['criteria'][0]['value']==0
    assert result['eligibility']['criteria'][0]['status']=='NOT_SATISFIED'
    source=admin.post('/api/documents/upload',files={'file':('synthetic-salary.txt',b'Monthly income: 50000')},data={'application_id':identifier})
    assert source.status_code==201
    assert admin.post(f"/api/documents/{source.json()['id']}/review").status_code==200
    result=admin.post('/api/eligibility/assess',json={'application_id':identifier}).json()
    assert result['eligibility']['criteria'][0]['value']==1
    assert result['eligibility']['criteria'][0]['status']=='SATISFIED'
    assert result['financial']['monthly_income'] is None  # OCR/text candidates never auto-verify income.
