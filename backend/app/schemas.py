from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(default='Loan analyst', min_length=2, max_length=100)


class ApplicantInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    monthly_income: float | None = Field(default=None, ge=0, le=1e10)
    monthly_debt: float | None = Field(default=None, ge=0, le=1e10)
    monthly_expenses: float | None = Field(default=None, ge=0, le=1e10)
    asset_value: float | None = Field(default=None, gt=0, le=1e12)
    asset_verified: bool = False
    employment_months: int | None = Field(default=None, ge=0, le=900)
    credit_score: int | None = Field(default=None, ge=300, le=900)
    credit_utilization: float | None = Field(default=None, ge=0, le=100)
    missed_payments: int | None = Field(default=None, ge=0, le=100)
    income_verified: bool = False
    credit_verified: bool = False
    income_conflict: bool = False


class ApplicationInput(BaseModel):
    applicant_id: int
    product_id: int
    amount: float = Field(gt=0, le=1e12)
    tenure_months: int = Field(ge=1, le=600)
    annual_rate: float | None = Field(default=None, ge=0, le=100)
    profile: Profile


class ApplicationRef(BaseModel):
    application_id: int


class QueryInput(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    product_id: int | None = None
    application_id: int | None = None


class ReviewInput(BaseModel):
    application_id: int
    assessment_id: int
    status: Literal['REVIEWED', 'MORE_INFORMATION_REQUIRED']
    comment: str = Field(min_length=5, max_length=5000)


class DecisionInput(BaseModel):
    decision: Literal['APPROVED', 'REJECTED', 'DEFERRED']
    rationale: str = Field(min_length=10, max_length=5000)


class EntityCorrectionInput(BaseModel):
    value: float = Field(ge=0, le=1e12)
    reason: str = Field(min_length=5, max_length=1000)


class Rule(BaseModel):
    key: Literal['monthly_income', 'dti', 'lti', 'ltv', 'repayment_burden', 'credit_score', 'employment_months', 'amount', 'tenure_months', 'reviewed_documents']
    label: str = Field(min_length=2, max_length=100)
    operator: Literal['min', 'max']
    threshold: float = Field(ge=0)
    document_id: int
    page: int = Field(ge=1)
    quote: str = Field(min_length=5, max_length=2000)


class PolicyConfig(BaseModel):
    policy_version: str = Field(min_length=1, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=100)
    criteria: list[Rule] = Field(min_length=1, max_length=30)
