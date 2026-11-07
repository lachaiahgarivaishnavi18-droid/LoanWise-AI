"""Each graph node validates its own payload before the shared state is updated."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field


class Payload(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Understanding(Payload):
    amount:float
    product:str
    missing_fields:list[str]


class DocumentStatus(Payload):
    id:int
    reviewed:bool
    warnings:list[str]


class Documents(Payload):
    documents:list[DocumentStatus]
    unreviewed:int
    income_candidates_conflict:bool
    note:str


class Financial(Payload):
    monthly_income:float|None
    monthly_debt:float|None
    monthly_expenses:float|None
    dti:float|None
    lti:float|None
    ltv:float|None
    emi:float|None
    disposable_income:float|None
    repayment_burden:float|None
    assumptions:list[str]
    currency:str


class CreditHistory(Payload):
    verified:bool
    credit_score:int|None
    synthetic:bool
    note:str


class Evidence(Payload):
    chunk_id:int
    document_id:int
    title:str
    page:int
    section:str
    version:str
    effective_date:str
    uploaded_at:str
    source_type:str
    permission:str
    text:str
    score:float
    synthetic:bool
    retrieval_strategy:str|None=None
    semantic_score:float|None=None
    keyword_score:float|None=None
    reranker_score:float|None=None


class Retrieval(Payload):
    evidence:list[Evidence]


class Contribution(Payload):
    feature:str
    value:float
    contribution:float
    direction:Literal['raises model score','lowers model score']


class Risk(Payload):
    model_name:str
    version:str
    synthetic_model:bool
    features:dict[str,float|None]
    missing_features:list[str]
    limitations:list[str]
    timestamp:str
    score:float|None=Field(ge=0,le=1)
    category:Literal['LOW RISK','MODERATE RISK','HIGHER RISK','INSUFFICIENT INFORMATION']
    contributions:list[Contribution]
    thresholds:dict[str,float|str]|None=None
    baseline:float|None=None
    explanation_units:str|None=None
    restricted_features:list[str]=Field(default_factory=list)


class Explainability(Payload):
    contributions:list[Contribution]
    units:str|None
    limitations:list[str]


class Criterion(Payload):
    key:str
    label:str
    operator:Literal['min','max']
    threshold:float
    document_id:int
    page:int
    quote:str
    value:float|None
    status:Literal['SATISFIED','NOT_SATISFIED','UNKNOWN','CONFLICTING','NEEDS_HUMAN_REVIEW']
    evidence_valid:bool
    document_title:str|None
    policy_version:str


class Eligibility(Payload):
    criteria:list[Criterion]
    overall_status:Literal['ELIGIBILITY CONDITIONS SATISFIED — HUMAN REVIEW REQUIRED','POTENTIAL ELIGIBILITY ISSUES','INSUFFICIENT INFORMATION','CONFLICTING INFORMATION','MANUAL REVIEW REQUIRED']
    human_review_required:Literal[True]


class Validation(Payload):
    unsupported_criteria:list[str]
    income_conflict:bool
    evidence_coverage:float=Field(ge=0,le=1)
    limitations:str


class Report(Payload):
    summary:str
    synthetic:bool


class HumanReview(Payload):
    required:Literal[True]
    unresolved:list[str]
    unreviewed_documents:int
    automatic_decision:None


class Orchestrator(Payload):
    complete:bool
    agent_count:int
    requires_human_review:Literal[True]


SCHEMAS=dict(zip(['Application understanding','Document processing','Financial profile','Credit history','Policy retrieval','Credit risk','Explainable AI','Eligibility assessment','Evidence validation','Report generation','Human review support','Orchestrator'],[Understanding,Documents,Financial,CreditHistory,Retrieval,Risk,Explainability,Eligibility,Validation,Report,HumanReview,Orchestrator]))
