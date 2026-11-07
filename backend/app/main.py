import hashlib
import secrets
import time
from collections import defaultdict, Counter, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select, func
from sqlalchemy.orm import Session as DBSession
from .config import settings
from .database import Base, engine, get_db, SessionLocal,ensure_schema
from .models import *
from .schemas import *
from .security import current_user, roles, hash_password, verify_password, applicant_access, application_access, audit, policy_access,evidence_access
from .seed import seed
from ai.financial import financial_features
from ai.documents import extract, index_document, MAX_BYTES
from ai.retrieval import retrieve, grounded_answer
from ai.orchestration import run_assessment
from ml.pipeline import predict, load_model
from ai.provenance import input_fingerprint
from ai.eligibility import threshold_in_quote
from .normalized_services import initialize_roles, persist_prediction


@asynccontextmanager
async def lifespan(app):
    ensure_schema()
    with SessionLocal() as db:
        initialize_roles(db)
        if settings.demo_mode:
            seed(db)
        db.commit()
    yield


app = FastAPI(title='LoanWise AI', version='0.1.0', lifespan=lifespan, description='Explainable credit decision support research prototype. Human review required.')
app.add_middleware(CORSMiddleware, allow_origins=[settings.allowed_origin], allow_credentials=True, allow_methods=['GET', 'POST', 'PUT', 'DELETE'], allow_headers=['Content-Type'])
buckets = defaultdict(deque)


@app.middleware('http')
async def security_headers(request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin != settings.allowed_origin:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
    # Single-process development limiter. Use a shared reverse-proxy limiter in production.
    key = (request.client.host if request.client else 'unknown', 'auth' if '/auth/' in request.url.path else 'api')
    stamp = time.monotonic()
    queue = buckets[key]
    while queue and queue[0] < stamp - 60:
        queue.popleft()
    if len(queue) >= (30 if key[1] == 'auth' else 180):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Rate limit exceeded. Try again in one minute.'}, status_code=429)
    queue.append(stamp)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


def public_user(user):
    return {'id': user.id, 'name': user.name, 'email': user.email, 'role': user.role}


def product_view(product):
    return {'id':product.id,'name':product.name,'description':product.description,'policy_version':product.policy_version,'policy_revision':product.active_version.revision if product.active_version else None,'jurisdiction':product.jurisdiction,'criteria':product.criteria,'synthetic':product.synthetic}


def execution_view(db,user,item):
    try:
        evidence_access(db,user,item.output)
        output=item.output
    except HTTPException:
        output={'redacted':True,'reason':'Supporting source access is no longer available to this role'}
    return {'id':item.id,'application_id':item.application_id,'name':item.name,'status':item.status,'duration_ms':item.duration_ms,'output':output,'retries':item.retries,'created_at':item.created_at}


def review_view(db,user,record):
    assessment=db.get(Assessment,record.assessment_id)
    try:
        evidence_access(db,user,assessment.result)
        comment=record.comment
        decision=db.scalar(select(Decision).where(Decision.review_id==record.id))
    except HTTPException:
        comment='Supporting policy source access has been revoked; review text is withheld.'
        decision=None
    return {'id':record.id,'application_id':record.application_id,'assessment_id':record.assessment_id,'status':record.status,'comment':comment,'reviewer_id':record.reviewer_id,'created_at':record.created_at,'human_decision':decision}


def app_view(db, item):
    applicant = db.get(Applicant, item.applicant_id)
    product = db.get(Product, item.product_id)
    return {'id': item.id, 'applicant_id': item.applicant_id, 'applicant_name': applicant.name, 'reference': applicant.reference, 'product_id': item.product_id, 'product_name': product.name, 'amount': item.amount, 'tenure_months': item.tenure_months, 'annual_rate': item.annual_rate, 'profile': item.profile, 'status': item.status, 'synthetic': item.synthetic, 'created_at': item.created_at}


def owned_applications(db, user):
    query = select(Application).join(Applicant)
    if user.role != 'admin':
        query = query.where(Applicant.owner_id == user.id)
    return query


def doc_access(db, user, identifier):
    doc = db.get(Document, identifier)
    if not doc:
        raise HTTPException(404, 'Document not found')
    if doc.kind=='policy' and not policy_access(db,user,doc):
        raise HTTPException(404,'Document not found')
    if doc.application_id:
        application_access(db, user, doc.application_id)
    elif doc.kind != 'policy' and doc.owner_id != user.id and user.role != 'admin':
        raise HTTPException(404, 'Document not found')
    return doc


def doc_view(doc, full=False):
    result = {key: getattr(doc, key) for key in ['id', 'application_id', 'title', 'kind', 'version', 'effective_date', 'product_id', 'reviewed', 'synthetic', 'created_at']}
    result['extraction'] = doc.extraction
    result['page_count'] = len(doc.pages)
    result['permissions']=[permission.role_name for permission in doc.permission_records] if doc.kind=='policy' else []
    if full:
        result['pages'] = doc.pages
    return result


@app.get('/api/health')
def health(db: DBSession = Depends(get_db)):
    db.execute(select(1))
    return {'status': 'ok', 'demo_mode': settings.demo_mode, 'retrieval_mode': settings.retrieval_mode, 'llm_mode': 'extractive', 'model_ready': load_model() is not None,'ocr_enabled':settings.ocr_enabled,'ocr_engine':'RapidOCR ONNX CPU' if settings.ocr_enabled else None}


@app.post('/api/auth/register', status_code=201)
def register(body: Credentials, db: DBSession = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, 'An account with this email already exists')
    user = User(email=email, name=body.name, password_hash=hash_password(body.password), role='analyst')
    db.add(user); db.flush(); audit(db, user, 'register', user.id); db.commit()
    return public_user(user)


@app.post('/api/auth/login')
def login(body: Credentials, response: Response, db: DBSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # Equal-cost password work even for an unknown user.
    valid = verify_password(body.password, user.password_hash) if user else bool(hash_password(body.password) and False)
    if not valid:
        raise HTTPException(401, 'Invalid email or password')
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id, expires=(datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)).isoformat()))
    audit(db, user, 'login', user.id); db.commit()
    response.set_cookie('loanwise_session', token, httponly=True, secure=settings.cookie_secure, samesite='lax', max_age=settings.session_hours * 3600, path='/')
    return public_user(user)


@app.post('/api/auth/logout')
def logout(request: Request, response: Response, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = db.get(Session, hashlib.sha256(request.cookies.get('loanwise_session', '').encode()).hexdigest())
    if item:
        db.delete(item)
    audit(db, user, 'logout', user.id); db.commit()
    response.delete_cookie('loanwise_session', path='/')
    return {'message': 'Signed out'}


@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    return public_user(user)


@app.get('/api/products')
def products(db: DBSession = Depends(get_db), user=Depends(current_user)):
    result=[product_view(p) for p in db.scalars(select(Product)).all()]
    for item in result:
        if user.role!='admin':
            item['criteria']=[rule for rule in item['criteria'] if policy_access(db,user,db.get(Document,rule['document_id']))]
    return result


@app.put('/api/products/{identifier}/criteria')
def configure_policy(identifier: int, body: PolicyConfig, db: DBSession = Depends(get_db), user=Depends(roles('admin'))):
    product = db.get(Product, identifier)
    if not product:
        raise HTTPException(404, 'Product not found')
    for rule in body.criteria:
        doc = db.get(Document, rule.document_id)
        passage = next((p['text'] for p in doc.pages if p['page'] == rule.page), '') if doc else ''
        if not doc or doc.kind != 'policy' or not doc.reviewed or doc.product_id != identifier or doc.version != body.policy_version or rule.quote not in passage or not threshold_in_quote(rule.threshold, rule.quote):
            raise HTTPException(422, f'{rule.label}: a reviewed matching policy version and exact source quote containing the threshold are required')
    from .normalized_services import configure_product
    configure_product(product,body.policy_version,body.jurisdiction,[r.model_dump() for r in body.criteria])
    audit(db, user, 'configure_policy', identifier); db.commit()
    return product_view(product)


@app.post('/api/applicants', status_code=201)
def create_applicant(body: ApplicantInput, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = Applicant(owner_id=user.id, name=body.name, reference='LW-' + secrets.token_hex(4).upper(), synthetic=settings.demo_mode)
    db.add(item); db.flush(); audit(db, user, 'create_applicant', item.id); db.commit()
    return item


@app.get('/api/applicants')
def applicants(q: str = '', page: int = 1, limit: int = 25, db: DBSession = Depends(get_db), user=Depends(current_user)):
    query = select(Applicant)
    if user.role != 'admin':
        query = query.where(Applicant.owner_id == user.id)
    if q:
        query = query.where(Applicant.name.icontains(q[:100]))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items': db.scalars(query.order_by(Applicant.id.desc()).offset(max(page - 1, 0) * min(max(limit, 1), 100)).limit(min(max(limit, 1), 100))).all(), 'total': total}


@app.get('/api/applicants/{identifier}')
def applicant(identifier: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = applicant_access(db, user, identifier)
    return {'applicant': item, 'applications': [app_view(db, a) for a in db.scalars(select(Application).where(Application.applicant_id == identifier)).all()]}


@app.put('/api/applicants/{identifier}')
def update_applicant(identifier: int, body: ApplicantInput, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = applicant_access(db, user, identifier); item.name = body.name
    audit(db, user, 'update_applicant', identifier); db.commit()
    return item


@app.post('/api/applications', status_code=201)
def create_application(body: ApplicationInput, db: DBSession = Depends(get_db), user=Depends(current_user)):
    applicant_access(db, user, body.applicant_id)
    if not db.get(Product, body.product_id):
        raise HTTPException(422, 'Select an existing loan product')
    item = Application(**body.model_dump(), synthetic=settings.demo_mode)
    db.add(item); db.flush(); audit(db, user, 'create_application', item.id); db.commit()
    return app_view(db, item)


@app.get('/api/applications')
def applications(q: str = '', product_id: int | None = None, page: int = 1, limit: int = 25, db: DBSession = Depends(get_db), user=Depends(current_user)):
    query = owned_applications(db, user)
    if q:
        query = query.where(Applicant.name.icontains(q[:100]) | Applicant.reference.icontains(q[:100]))
    if product_id:
        query = query.where(Application.product_id == product_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Application.id.desc()).offset(max(page - 1, 0) * min(max(limit, 1), 100)).limit(min(max(limit, 1), 100))).all()
    return {'items': [app_view(db, a) for a in items], 'total': total}


@app.get('/api/applications/{identifier}')
def application(identifier: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    return app_view(db, application_access(db, user, identifier))


@app.put('/api/applications/{identifier}')
def update_application(identifier: int, body: ApplicationInput, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = application_access(db, user, identifier)
    applicant_access(db, user, body.applicant_id)
    if not db.get(Product, body.product_id):
        raise HTTPException(422, 'Product not found')
    for key, value in body.model_dump().items():
        try:
            setattr(item, key, value)
        except ValueError as error:
            db.rollback()
            raise HTTPException(422,str(error))
    item.status = 'Updated — reassessment required'
    audit(db, user, 'update_application', identifier); db.commit()
    return app_view(db, item)


@app.post('/api/documents/upload', status_code=201)
@app.post('/api/rag/ingest', status_code=201)
async def upload(file: UploadFile = File(...), application_id: int | None = Form(None), kind: str = Form('financial'), product_id: int | None = Form(None), version: str = Form('1'), effective_date: str | None = Form(None), db: DBSession = Depends(get_db), user=Depends(current_user)):
    if kind not in ('financial', 'policy'):
        raise HTTPException(422, 'Invalid document kind')
    if kind == 'policy':
        if user.role != 'admin':
            raise HTTPException(403, 'Only administrators can ingest policies')
        if application_id is not None:
            raise HTTPException(422, 'Shared policies cannot be attached to private applicant records')
        if not product_id or not db.get(Product, product_id) or not effective_date:
            raise HTTPException(422, 'Policy product and effective date are required')
        try:
            date.fromisoformat(effective_date)
        except ValueError:
            raise HTTPException(422, 'Effective date must be YYYY-MM-DD')
    elif application_id is None:
        raise HTTPException(422, 'Financial documents require an application')
    elif product_id is not None:
        raise HTTPException(422,'Financial documents inherit their product from the application; omit product_id')
    if application_id is not None:
        application_access(db, user, application_id)
    data = await file.read(MAX_BYTES + 1)
    pages, extraction = await run_in_threadpool(extract,file.filename or '',data)
    path = ''
    if settings.document_storage == 'filesystem':
        storage = Path(settings.storage_dir); storage.mkdir(parents=True, exist_ok=True)
        path = storage / (secrets.token_hex(16) + Path(file.filename).suffix.lower())
        path.write_bytes(data)
    item = Document(owner_id=user.id, application_id=application_id, title=Path(file.filename).name[:200], kind=kind, path=str(path), product_id=product_id, version=version[:100], effective_date=effective_date, pages=pages, extraction=extraction, synthetic=settings.demo_mode)
    if settings.document_storage == 'database':
        item.content_bytes=data
    db.add(item); db.flush(); audit(db, user, 'upload_document', item.id); db.commit()
    return doc_view(item, True)


@app.get('/api/documents')
@app.get('/api/rag/documents')
def documents(kind: str | None = None, application_id: int | None = None, page: int = 1, db: DBSession = Depends(get_db), user=Depends(current_user)):
    query = select(Document)
    if user.role != 'admin':
        allowed = owned_applications(db, user).with_only_columns(Application.id)
        from .normalized_models import DocumentPermission
        shared=select(DocumentPermission.document_id).where(DocumentPermission.role_name==user.role)
        query = query.where(Document.application_id.in_(allowed) | ((Document.kind == 'policy') & Document.id.in_(shared)))
    if kind:
        query = query.where(Document.kind == kind)
    if application_id:
        application_access(db, user, application_id)
        query = query.where(Document.application_id == application_id)
    return [doc_view(d) for d in db.scalars(query.order_by(Document.id.desc()).offset(max(page - 1, 0) * 30).limit(30)).all()]


@app.get('/api/documents/{identifier}')
def document(identifier: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    return doc_view(doc_access(db, user, identifier), True)


@app.get('/api/documents/{identifier}/download')
def download_document(identifier: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    doc = doc_access(db, user, identifier)
    if doc.content_bytes is not None:
        from urllib.parse import quote
        return Response(content=doc.content_bytes,media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(doc.title,safe='')})
    if not doc.path or not Path(doc.path).is_file():
        raise HTTPException(404, 'Synthetic source is available as extracted text only')
    return FileResponse(doc.path, filename=doc.title, media_type='application/octet-stream')


@app.post('/api/documents/{identifier}/extract')
def reextract(identifier: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    doc = doc_access(db, user, identifier)
    if doc.kind == 'policy' and user.role != 'admin':
        raise HTTPException(403, 'Administrator required')
    if not doc.path and doc.content_bytes is None:
        return doc_view(doc, True)
    doc.pages, doc.extraction = extract(doc.title, doc.content_bytes if doc.content_bytes is not None else Path(doc.path).read_bytes())
    doc.reviewed = False
    index_document(db, doc); audit(db, user, 'extract_document', identifier); db.commit()
    return doc_view(doc, True)


@app.post('/api/documents/{identifier}/review')
def review_document(identifier: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    doc = doc_access(db, user, identifier)
    if doc.kind == 'policy' and user.role != 'admin':
        raise HTTPException(403, 'Only administrators can review policies')
    if doc.extraction.get('quarantined') or not any(p['text'].strip() for p in doc.pages):
        raise HTTPException(422, 'Quarantined or empty documents cannot be indexed')
    doc.reviewed = True
    count = index_document(db, doc)
    audit(db, user, 'review_document', identifier); db.commit()
    return {'document': doc_view(doc, True), 'indexed_chunks': count, 'note': 'Extracted candidates do not overwrite application financial values. Correct and verify the application explicitly.'}


@app.put('/api/documents/{identifier}/entities/{entity_index}')
def correct_entity(identifier: int, entity_index: int, body: EntityCorrectionInput, db: DBSession = Depends(get_db), user=Depends(current_user)):
    import copy
    doc = doc_access(db, user, identifier)
    if doc.kind != 'financial':
        raise HTTPException(422, 'Policy text must be replaced by a new version, not an entity correction')
    extraction = copy.deepcopy(doc.extraction)
    entities = extraction.get('entities', [])
    if entity_index < 0 or entity_index >= len(entities):
        raise HTTPException(404, 'Extraction candidate not found')
    entity = entities[entity_index]
    history = entity.setdefault('correction_history', [])
    history.append({'previous_value': entity['value'], 'corrected_value': body.value, 'reason': body.reason, 'reviewer_id': user.id, 'timestamp': now()})
    entity['value'] = body.value
    entity['verified'] = False
    doc.extraction = extraction
    doc.reviewed = False
    audit(db, user, 'correct_extraction_candidate', doc.id); db.commit()
    return doc_view(doc, True)


@app.get('/api/financial/{application_id}')
def financial(application_id: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    return financial_features(application_access(db, user, application_id))


@app.post('/api/financial/analyze')
def analyze(body: ApplicationRef, db: DBSession = Depends(get_db), user=Depends(current_user)):
    return financial_features(application_access(db, user, body.application_id))


@app.post('/api/credit-risk/predict')
@app.post('/api/explainability/shap')
def risk_predict(body: ApplicationRef, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = application_access(db, user, body.application_id)
    product=db.get(Product,item.product_id)
    result = predict(item, financial_features(item),allowed_features=settings.model_feature_policies.get(product.jurisdiction,[]))
    record = persist_prediction(db, item.id, result)
    db.commit()
    return {**result, 'prediction_id': record.id}


@app.get('/api/credit-risk/{application_id}')
@app.get('/api/explainability/{application_id}')
def risk(application_id: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = application_access(db, user, application_id)
    product=db.get(Product,item.product_id)
    return predict(item, financial_features(item),allowed_features=settings.model_feature_policies.get(product.jurisdiction,[]))


@app.get('/api/models/evaluation')
@app.get('/api/reports/model-performance')
def model_evaluation(user=Depends(current_user)):
    artifact = load_model()
    return artifact['report'] if artifact else {'models': {}, 'limitations': ['No model trained. Run python -m ml.pipeline from backend.']}


@app.post('/api/eligibility/assess')
@app.post('/api/agents/run')
def assess(body: ApplicationRef, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = application_access(db, user, body.application_id)
    try:
        result = run_assessment(db, item,user)
    except PermissionError:
        raise HTTPException(403,'This role cannot access a policy required by the assessment')
    except RuntimeError as error:
        raise HTTPException(503, str(error))
    audit(db, user, 'assess', item.id); db.commit()
    return result


@app.get('/api/eligibility/{application_id}')
def assessment(application_id: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    application_access(db, user, application_id)
    record = db.scalar(select(Assessment).where(Assessment.application_id == application_id).order_by(Assessment.id.desc()))
    if record:
        evidence_access(db,user,record.result)
    return record.result if record else None


@app.post('/api/rag/query')
def query(body: QueryInput, db: DBSession = Depends(get_db), user=Depends(current_user)):
    product_id = body.product_id
    item=None
    if body.application_id:
        item = application_access(db, user, body.application_id)
        product_id = item.product_id
    # Applicant documents are never placed in the shared policy corpus.
    answer = grounded_answer(body.question, retrieve(db, body.question, product_id,role=user.role))
    if item:
        from ai.assistant import application_answer
        answer=application_answer(db,user,item,body.question,answer)
    record = RagQuery(user_id=user.id, question=body.question, response=answer)
    db.add(record); db.flush(); audit(db, user, 'rag_query', record.id); db.commit()
    return {**answer, 'query_id': record.id}


@app.get('/api/rag/evidence/{identifier}')
def query_evidence(identifier: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = db.get(RagQuery, identifier)
    if not item or item.user_id != user.id:
        raise HTTPException(404, 'Query not found')
    evidence_access(db,user,item.response)
    context=item.response.get('application_context')
    if context:
        application_access(db,user,context['application_id'])
    return item.response


@app.get('/api/agents/executions')
def executions(application_id: int | None = None, db: DBSession = Depends(get_db), user=Depends(current_user)):
    allowed = owned_applications(db, user).with_only_columns(Application.id)
    query = select(AgentExecution).where(AgentExecution.application_id.in_(allowed))
    if application_id:
        application_access(db, user, application_id)
        query = query.where(AgentExecution.application_id == application_id)
    return [execution_view(db,user,item) for item in db.scalars(query.order_by(AgentExecution.id.desc()).limit(100)).all()]


@app.get('/api/agents/executions/{identifier}')
def execution(identifier: int, db: DBSession = Depends(get_db), user=Depends(current_user)):
    item = db.get(AgentExecution, identifier)
    if not item:
        raise HTTPException(404, 'Execution not found')
    application_access(db, user, item.application_id)
    return execution_view(db,user,item)


@app.post('/api/reviews', status_code=201)
def create_review(body: ReviewInput, db: DBSession = Depends(get_db), user=Depends(roles('reviewer', 'admin'))):
    item = application_access(db, user, body.application_id)
    assessment = db.get(Assessment, body.assessment_id)
    latest = db.scalar(select(Assessment).where(Assessment.application_id == item.id).order_by(Assessment.id.desc()))
    if not assessment or assessment.application_id != item.id or latest.id != assessment.id or assessment.result.get('input_fingerprint') != input_fingerprint(db, item):
        raise HTTPException(422, 'Review must reference the latest current assessment for this application')
    evidence_access(db,user,assessment.result)
    record = Review(**body.model_dump(), reviewer_id=user.id)
    db.add(record); db.flush(); audit(db, user, 'create_review', record.id); db.commit()
    return record


@app.get('/api/reviews')
def reviews(db: DBSession = Depends(get_db), user=Depends(current_user)):
    allowed = owned_applications(db, user).with_only_columns(Application.id)
    records = db.scalars(select(Review).where(Review.application_id.in_(allowed)).order_by(Review.id.desc()).limit(100)).all()
    return [review_view(db,user,record) for record in records]


@app.put('/api/reviews/{identifier}')
def update_review(identifier: int, body: ReviewInput, db: DBSession = Depends(get_db), user=Depends(roles('reviewer', 'admin'))):
    record = db.get(Review, identifier)
    if not record or record.reviewer_id != user.id:
        raise HTTPException(404, 'Review not found')
    application_access(db,user,record.application_id)
    evidence_access(db,user,db.get(Assessment,record.assessment_id).result)
    if db.scalar(select(Decision).where(Decision.review_id == record.id)):
        raise HTTPException(409, 'A finalized review is immutable')
    if record.application_id != body.application_id or record.assessment_id != body.assessment_id:
        raise HTTPException(422, 'Cannot change review application or assessment')
    record.comment = body.comment; record.status = body.status
    audit(db, user, 'update_review', identifier); db.commit()
    return record


@app.post('/api/reviews/{identifier}/decision', status_code=201)
def decision(identifier: int, body: DecisionInput, db: DBSession = Depends(get_db), user=Depends(roles('reviewer', 'admin'))):
    review = db.get(Review, identifier)
    if not review:
        raise HTTPException(404, 'Review not found')
    application = application_access(db, user, review.application_id)
    latest = db.scalar(select(Assessment).where(Assessment.application_id == application.id).order_by(Assessment.id.desc()))
    if review.status != 'REVIEWED' or not latest or latest.id != review.assessment_id or latest.result.get('input_fingerprint') != input_fingerprint(db, application):
        raise HTTPException(422, 'A current completed human review is required')
    evidence_access(db,user,latest.result)
    if db.scalar(select(Decision).where(Decision.review_id == identifier)):
        raise HTTPException(409, 'A human decision is already recorded')
    record = Decision(review_id=identifier, reviewer_id=user.id, **body.model_dump())
    db.add(record); audit(db, user, 'human_decision', identifier); db.commit()
    return record


@app.get('/api/reports/dashboard')
def dashboard(db: DBSession = Depends(get_db), user=Depends(current_user)):
    items = db.scalars(owned_applications(db, user)).all()
    ids = [a.id for a in items]
    assessments = db.scalars(select(Assessment).where(Assessment.application_id.in_(ids)).order_by(Assessment.id)).all()
    latest = {a.application_id: a.result for a in assessments}
    review_ids = set(db.scalars(select(Review.application_id).where(Review.application_id.in_(ids))).all())
    durations = db.scalars(select(AgentExecution.duration_ms).where(AgentExecution.application_id.in_(ids))).all()
    return {'total': len(items), 'awaiting_review': len(set(ids) - review_ids), 'issues': sum('ISSUES' in a.status or 'CONFLICTING' in a.status for a in items), 'incomplete': sum(a.profile.get('monthly_income') is None for a in items), 'average_agent_ms': round(sum(durations) / len(durations), 2) if durations else None, 'risk_distribution': dict(Counter(a['risk']['category'] for a in latest.values())), 'product_distribution': dict(Counter(db.get(Product, a.product_id).name for a in items)), 'recent': [app_view(db, a) for a in items[-6:][::-1]], 'assessment_count': len(latest), 'synthetic': settings.demo_mode, 'review_count': len(review_ids), 'evidence_coverage': round(sum(a['validation']['evidence_coverage'] for a in latest.values()) / len(latest), 3) if latest else None}


@app.get('/api/reports/applications')
def report_applications(db: DBSession = Depends(get_db), user=Depends(current_user)):
    return [app_view(db, a) for a in db.scalars(owned_applications(db, user).limit(1000)).all()]


@app.get('/api/reports/fairness')
def fairness(user=Depends(current_user)):
    artifact=load_model()
    return {'status': 'NOT_EVALUATED', 'reason': 'Real-world demographic fairness is unevaluated. Random synthetic cohort diagnostics are development checks only; sensitive attributes are not inferred.', 'metrics_available_in_training_module': ['demographic parity difference', 'equal opportunity difference', 'equalized odds difference', 'group FPR and FNR'], 'synthetic_diagnostics':artifact['report'].get('synthetic_fairness') if artifact else None,'legal_compliance_claim': False}


@app.get('/api/reports/retrieval')
def retrieval_report(db: DBSession = Depends(get_db), user=Depends(current_user)):
    from ai.evaluation import evaluate_retrieval
    return evaluate_retrieval(db,role=user.role)


@app.get('/api/settings')
def system_settings(db: DBSession = Depends(get_db), user=Depends(roles('admin'))):
    return {'demo_mode': settings.demo_mode, 'llm_provider': settings.llm_provider, 'active_answer_mode': 'extractive', 'retrieval_mode': settings.retrieval_mode, 'retention_days': settings.retention_days, 'cookie_secure': settings.cookie_secure, 'users': [public_user(u) for u in db.scalars(select(User)).all()], 'feature_allowlist': ['dti', 'lti', 'employment_months', 'credit_utilization', 'missed_payments'], 'audit': db.scalars(select(Audit).order_by(Audit.id.desc()).limit(100)).all()}


@app.put('/api/users/{identifier}/role')
def change_role(identifier: int, role: Literal['analyst', 'reviewer', 'admin'], db: DBSession = Depends(get_db), user=Depends(roles('admin'))):
    item = db.get(User, identifier)
    if not item:
        raise HTTPException(404, 'User not found')
    if item.id == user.id:
        raise HTTPException(422, 'Cannot change your own role')
    item.role = role; audit(db, user, 'change_role', identifier); db.commit()
    return public_user(item)


from .ledger_api import router as ledger_router
app.include_router(ledger_router)
from .history_api import router as history_router
app.include_router(history_router)
