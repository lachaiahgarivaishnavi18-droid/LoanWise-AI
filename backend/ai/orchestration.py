import time
from typing import TypedDict, Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from sqlalchemy import select
from app.models import Product, Document, AgentExecution, Assessment
from .financial import financial_features
from .eligibility import evaluate
from .retrieval import retrieve
from ml.pipeline import predict
from .provenance import input_fingerprint
from .agent_schemas import SCHEMAS


class AgentOutput(BaseModel):
    agent: str
    status: Literal['completed', 'needs_review', 'failed'] = 'completed'
    data: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    evidence_ids: list[int] = Field(default_factory=list)


class State(TypedDict, total=False):
    application_id: int
    outputs: dict[str, dict]


NAMES = ['Application understanding', 'Document processing', 'Financial profile', 'Credit history', 'Policy retrieval', 'Credit risk', 'Explainable AI', 'Eligibility assessment', 'Evidence validation', 'Report generation', 'Human review support', 'Orchestrator']


def run_assessment(db, application,user=None):
    product = db.get(Product, application.product_id)
    if user:
        from app.security import policy_access
        if any(not policy_access(db,user,db.get(Document,rule['document_id'])) for rule in product.criteria):
            raise PermissionError('Required policy access denied')
    documents = db.scalars(select(Document).where(Document.application_id == application.id)).all()
    claimed_income = application.profile.get('monthly_income')
    candidate_income = [e.get('value') for d in documents for e in d.extraction.get('entities', []) if e.get('field') in ('monthly income', 'salary')]
    document_conflicts = [value for value in candidate_income if claimed_income is not None and value is not None and abs(value - claimed_income) > .01]
    if document_conflicts:
        application.profile_record.income_conflict=True

    def execute(name, state):
        previous = state.get('outputs', {})
        warnings = []
        if name == 'Application understanding':
            data = {'amount': application.amount, 'product': product.name, 'missing_fields': [k for k in ['monthly_income', 'monthly_debt', 'employment_months'] if application.profile.get(k) is None]}
        elif name == 'Document processing':
            data = {'documents': [{'id': d.id, 'reviewed': d.reviewed, 'warnings': d.extraction.get('warnings', [])} for d in documents], 'unreviewed': sum(not d.reviewed for d in documents), 'income_candidates_conflict': bool(document_conflicts), 'note': 'Unverified extracted contradictions require review; they never overwrite claimed income.'}
        elif name == 'Financial profile':
            data = financial_features(application)
        elif name == 'Credit history':
            data = {'verified': application.profile.get('credit_verified', False), 'credit_score': application.profile.get('credit_score'), 'synthetic': application.synthetic, 'note': 'No credit history or score is inferred.'}
        elif name == 'Policy retrieval':
            data = {'evidence': retrieve(db, 'income debt tenure principal employment eligibility', product.id, version=product.policy_version,role=user.role if user else 'admin')}
        elif name == 'Credit risk':
            from app.config import settings
            data = predict(application, previous['Financial profile']['data'],allowed_features=settings.model_feature_policies.get(product.jurisdiction,[]))
        elif name == 'Explainable AI':
            risk = previous['Credit risk']['data']
            data = {'contributions': risk['contributions'], 'units': risk.get('explanation_units'), 'limitations': risk['limitations']}
        elif name == 'Eligibility assessment':
            data = evaluate(db, application, product, previous['Financial profile']['data'])
        elif name == 'Evidence validation':
            criteria = previous['Eligibility assessment']['data']['criteria']
            data = {'unsupported_criteria': [c['key'] for c in criteria if not c['evidence_valid']], 'income_conflict': application.profile.get('income_conflict', False), 'evidence_coverage': sum(c['evidence_valid'] for c in criteria) / max(len(criteria), 1), 'limitations': 'Exact citation validation does not establish semantic or legal policy correctness.'}
        elif name == 'Report generation':
            eligibility = previous['Eligibility assessment']['data']
            data = {'summary': eligibility['overall_status'] + '. Authorized human review is required. Policy conditions, model indicators and source evidence are presented separately.', 'synthetic': application.synthetic}
        elif name == 'Human review support':
            data = {'required': True, 'unresolved': [c['label'] for c in previous['Eligibility assessment']['data']['criteria'] if c['status'] != 'SATISFIED'], 'unreviewed_documents': previous['Document processing']['data']['unreviewed'], 'automatic_decision': None}
        else:
            data = {'complete': len(previous) == 11, 'agent_count': 12, 'requires_human_review': True}
        data=SCHEMAS[name].model_validate(data).model_dump(exclude_unset=True)
        evidence = [e['chunk_id'] for e in data.get('evidence', [])]
        return AgentOutput(agent=name, data=data, warnings=warnings, evidence_ids=evidence)

    graph = StateGraph(State)
    for name in NAMES:
        def node(state, agent=name):
            start = time.perf_counter()
            attempts = 0
            while True:
                try:
                    result = execute(agent, state)
                    break
                except Exception:
                    if attempts >= 1:
                        db.add(AgentExecution(application_id=application.id, name=agent, status='failed', duration_ms=(time.perf_counter() - start) * 1000, output={'error': 'Agent failed; assessment withheld'}, retries=attempts))
                        db.commit()
                        raise RuntimeError(f'{agent} failed; no final assessment produced')
                    attempts += 1
            output = result.model_dump()
            db.add(AgentExecution(application_id=application.id, name=agent, status=result.status, duration_ms=round((time.perf_counter() - start) * 1000, 2), output=output, retries=attempts))
            return {'outputs': {**state.get('outputs', {}), agent: output}}
        graph.add_node(name, node)
    graph.set_entry_point(NAMES[0])
    for a, b in zip(NAMES, NAMES[1:]):
        graph.add_edge(a, b)
    graph.add_edge(NAMES[-1], END)
    state = graph.compile().invoke({'application_id': application.id, 'outputs': {}})
    outputs = state['outputs']
    get = lambda name: outputs[name]['data']
    result = {'application_id': application.id, 'synthetic': application.synthetic, 'product': product.name, 'financial': get('Financial profile'), 'risk': get('Credit risk'), 'eligibility': get('Eligibility assessment'), 'evidence': get('Policy retrieval')['evidence'], 'validation': get('Evidence validation'), 'review': get('Human review support'), 'summary': get('Report generation')['summary'], 'agent_count': len(outputs)}
    result.update(policy_version_id=product.active_version_id,policy_version=product.policy_version,policy_revision=product.active_version.revision if product.active_version else None,jurisdiction=product.jurisdiction)
    result['input_fingerprint'] = input_fingerprint(db, application)
    # Unreviewed documents prevent a clean condition-satisfied overall assessment.
    if result['review']['unreviewed_documents'] and result['eligibility']['overall_status'].startswith('ELIGIBILITY CONDITIONS'):
        result['eligibility']['overall_status'] = 'MANUAL REVIEW REQUIRED'
    result['summary'] = result['eligibility']['overall_status'] + '. Authorized human review is required. Policy conditions, model indicators and source evidence are presented separately.'
    record = Assessment(application_id=application.id, result=dict(result))
    application.status = result['eligibility']['overall_status']
    db.add(record); db.flush()
    from app.normalized_services import persist_assessment
    persist_assessment(db, record)
    result['assessment_id'] = record.id
    record.result = dict(result)
    db.commit()
    return result
