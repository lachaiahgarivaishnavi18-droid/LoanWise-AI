from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, JSON, Text, UniqueConstraint,Numeric,CheckConstraint,LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def now():
    return datetime.now(timezone.utc).isoformat()


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str]
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(ForeignKey('roles.name'), default='analyst')


class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[str]


class Applicant(Base):
    __tablename__ = 'applicants'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str]
    reference: Mapped[str] = mapped_column(unique=True)
    synthetic: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(default=now)


class Product(Base):
    __tablename__ = 'loan_products'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str]
    synthetic: Mapped[bool] = mapped_column(default=True)


class Application(Base):
    __tablename__ = 'loan_applications'
    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey('applicants.id'), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('loan_products.id'))
    amount: Mapped[float] = mapped_column(Numeric(18,2,asdecimal=False))
    tenure_months: Mapped[int]
    annual_rate: Mapped[float | None] = mapped_column(Numeric(7,4,asdecimal=False))
    status: Mapped[str] = mapped_column(default='Awaiting assessment')
    synthetic: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__=(CheckConstraint('amount > 0',name='ck_application_amount'),CheckConstraint('tenure_months BETWEEN 1 AND 600',name='ck_application_tenure'),CheckConstraint('annual_rate IS NULL OR annual_rate BETWEEN 0 AND 100',name='ck_application_rate'))


class Document(Base):
    __tablename__ = 'financial_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey('loan_applications.id'))
    title: Mapped[str]
    kind: Mapped[str]
    path: Mapped[str]
    content_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    version: Mapped[str]
    effective_date: Mapped[str | None]
    product_id: Mapped[int | None] = mapped_column(ForeignKey('loan_products.id'))
    reviewed: Mapped[bool] = mapped_column(default=False)
    synthetic: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__=(CheckConstraint("(kind = 'policy' AND product_id IS NOT NULL AND application_id IS NULL) OR (kind = 'financial' AND application_id IS NOT NULL AND product_id IS NULL)",name='ck_document_scope'),)


class Chunk(Base):
    __tablename__ = 'document_chunks'
    id: Mapped[int] = mapped_column(primary_key=True)
    section: Mapped[str]
    text: Mapped[str] = mapped_column(Text)


class Assessment(Base):
    __tablename__ = 'eligibility_assessments'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('loan_applications.id'), index=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class AgentExecution(Base):
    __tablename__ = 'agent_executions'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('loan_applications.id'), index=True)
    name: Mapped[str]
    status: Mapped[str]
    duration_ms: Mapped[float]
    output: Mapped[dict] = mapped_column(JSON)
    retries: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default=now)


class Review(Base):
    __tablename__ = 'human_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('loan_applications.id'), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey('eligibility_assessments.id'))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str]
    comment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__=(CheckConstraint("status IN ('REVIEWED','MORE_INFORMATION_REQUIRED')",name='ck_review_status'),)


class Decision(Base):
    __tablename__ = 'final_human_decisions'
    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('human_reviews.id'), unique=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    decision: Mapped[str]
    rationale: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__=(CheckConstraint("decision IN ('APPROVED','REJECTED','DEFERRED')",name='ck_human_decision'),)


class RagQuery(Base):
    __tablename__ = 'rag_queries'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    question: Mapped[str]
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class Audit(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str]
    resource: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)

# Relational mappings keep the public profile/policy/document API stable.
from . import normalized_models
