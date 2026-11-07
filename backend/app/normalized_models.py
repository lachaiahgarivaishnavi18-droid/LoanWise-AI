"""Operational facts are relational. JSON remains only in immutable audit/agent snapshots."""
from sqlalchemy import String, Text, Integer, Float, Boolean, Numeric, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import select
from .database import Base
from .models import now, User, Application, Product, Document, Chunk, Assessment, Review, RagQuery


class Row(Base):
    __abstract__ = True
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[str] = mapped_column(default=now)


class Role(Base):
    __tablename__ = 'roles'
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    description: Mapped[str]


class Permission(Base):
    __tablename__ = 'permissions'
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    description: Mapped[str]


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    role_name: Mapped[str] = mapped_column(ForeignKey('roles.name'), primary_key=True)
    permission_name: Mapped[str] = mapped_column(ForeignKey('permissions.name'), primary_key=True)


class ApplicantProfile(Row):
    __tablename__ = 'applicant_profiles'
    application_id: Mapped[int] = mapped_column(ForeignKey('loan_applications.id'), unique=True)
    currency: Mapped[str] = mapped_column(String(3), default='INR')
    asset_value: Mapped[float | None] = mapped_column(Numeric(18, 2, asdecimal=False))
    asset_verified: Mapped[bool] = mapped_column(default=False)
    income_conflict: Mapped[bool] = mapped_column(default=False)
    application = relationship('Application', back_populates='profile_record')
    incomes = relationship('IncomeRecord', lazy='selectin', cascade='all, delete-orphan', order_by='IncomeRecord.id')
    expenses = relationship('ExpenseRecord', lazy='selectin', cascade='all, delete-orphan', order_by='ExpenseRecord.id')
    liabilities = relationship('Liability', lazy='selectin', cascade='all, delete-orphan', order_by='Liability.id')
    employment = relationship('EmploymentRecord', lazy='selectin', cascade='all, delete-orphan', order_by='EmploymentRecord.id')
    credit_accounts = relationship('CreditAccount', lazy='selectin', cascade='all, delete-orphan', order_by='CreditAccount.id')
    __table_args__ = (CheckConstraint('asset_value IS NULL OR asset_value > 0', name='ck_profile_asset_positive'),)


class FinancialSource(Row):
    __abstract__ = True
    profile_id: Mapped[int] = mapped_column(ForeignKey('applicant_profiles.id'), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey('financial_documents.id'))
    source_type: Mapped[str] = mapped_column(default='USER_PROVIDED')


class IncomeRecord(FinancialSource):
    __tablename__ = 'income_records'
    amount: Mapped[float] = mapped_column(Numeric(18, 2, asdecimal=False))
    frequency: Mapped[str] = mapped_column(default='MONTHLY')
    verified: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (CheckConstraint('amount >= 0', name='ck_income_nonnegative'), CheckConstraint("frequency IN ('MONTHLY','ANNUAL','WEEKLY','FORTNIGHTLY')", name='ck_income_frequency'))


class ExpenseRecord(FinancialSource):
    __tablename__ = 'expense_records'
    monthly_amount: Mapped[float] = mapped_column(Numeric(18, 2, asdecimal=False))
    category: Mapped[str] = mapped_column(default='DECLARED_TOTAL')
    __table_args__ = (CheckConstraint('monthly_amount >= 0', name='ck_expense_nonnegative'),)


class Liability(FinancialSource):
    __tablename__ = 'liabilities'
    monthly_payment: Mapped[float] = mapped_column(Numeric(18, 2, asdecimal=False))
    outstanding_balance: Mapped[float | None] = mapped_column(Numeric(18, 2, asdecimal=False))
    __table_args__ = (CheckConstraint('monthly_payment >= 0', name='ck_liability_nonnegative'),)


class EmploymentRecord(FinancialSource):
    __tablename__ = 'employment_records'
    duration_months: Mapped[int] = mapped_column()
    __table_args__ = (CheckConstraint('duration_months >= 0 AND duration_months <= 900', name='ck_employment_duration'),)


class CreditAccount(FinancialSource):
    __tablename__ = 'credit_accounts'
    reliable_score: Mapped[int | None]
    utilization_percent: Mapped[float | None]
    reported_missed_payments: Mapped[int | None]
    verified: Mapped[bool] = mapped_column(default=False)
    repayments = relationship('RepaymentRecord', cascade='all, delete-orphan', order_by='RepaymentRecord.period')
    __table_args__ = (CheckConstraint('reliable_score IS NULL OR reliable_score BETWEEN 300 AND 900', name='ck_credit_score'), CheckConstraint('utilization_percent IS NULL OR utilization_percent BETWEEN 0 AND 100', name='ck_credit_utilization'), CheckConstraint('reported_missed_payments IS NULL OR reported_missed_payments >= 0', name='ck_credit_missed'))


class RepaymentRecord(Row):
    __tablename__ = 'repayment_records'
    credit_account_id: Mapped[int] = mapped_column(ForeignKey('credit_accounts.id'), index=True)
    period: Mapped[str] = mapped_column(String(10))
    status: Mapped[str]
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey('financial_documents.id'))
    __table_args__ = (UniqueConstraint('credit_account_id', 'period'), CheckConstraint("status IN ('PAID','MISSED','UNKNOWN')", name='ck_repayment_status'))


class PolicyVersion(Row):
    __tablename__ = 'policy_versions'
    product_id: Mapped[int] = mapped_column(ForeignKey('loan_products.id'), index=True)
    version: Mapped[str]
    revision: Mapped[int] = mapped_column(default=1)
    jurisdiction: Mapped[str] = mapped_column(default='SYNTHETIC DEMO')
    product = relationship('Product', foreign_keys=[product_id], back_populates='versions')
    criteria = relationship('EligibilityCriterion', lazy='selectin', cascade='all, delete-orphan', order_by='EligibilityCriterion.id')
    __table_args__ = (UniqueConstraint('product_id', 'version', 'revision'),)


class DocumentPage(Row):
    __tablename__ = 'document_pages'
    document_id: Mapped[int] = mapped_column(ForeignKey('financial_documents.id'), index=True)
    page_number: Mapped[int]
    revision: Mapped[int] = mapped_column(default=1)
    active: Mapped[bool] = mapped_column(default=True)
    text: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(default='text')
    ocr_confidence: Mapped[float | None]
    document = relationship('Document', back_populates='page_records')
    entities = relationship('ExtractedFinancialEntity', lazy='selectin', back_populates='page', cascade='all, delete-orphan', order_by='ExtractedFinancialEntity.ordinal')
    __table_args__ = (UniqueConstraint('document_id', 'page_number', 'revision'), CheckConstraint('page_number >= 1', name='ck_document_page_positive'))


class ExtractedFinancialEntity(Row):
    __tablename__ = 'extracted_financial_entities'
    document_page_id: Mapped[int] = mapped_column(ForeignKey('document_pages.id'), index=True)
    ordinal: Mapped[int]
    field: Mapped[str]
    value: Mapped[float | None]
    quote: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    page = relationship('DocumentPage', back_populates='entities')
    corrections = relationship('ExtractionCorrection', lazy='selectin', cascade='all, delete-orphan', order_by='ExtractionCorrection.id')


class ExtractionCorrection(Row):
    __tablename__ = 'extraction_corrections'
    entity_id: Mapped[int] = mapped_column(ForeignKey('extracted_financial_entities.id'), index=True)
    previous_value: Mapped[float | None]
    corrected_value: Mapped[float | None]
    reason: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))


class DocumentWarning(Row):
    __tablename__ = 'document_warnings'
    document_id: Mapped[int] = mapped_column(ForeignKey('financial_documents.id'), index=True)
    message: Mapped[str] = mapped_column(Text)


class KnowledgeSource(Row):
    __tablename__ = 'knowledge_sources'
    document_id: Mapped[int] = mapped_column(ForeignKey('financial_documents.id'), unique=True)
    source_type: Mapped[str]
    authorized: Mapped[bool] = mapped_column(default=True)
    source_uri: Mapped[str | None]


class PolicyDocument(Base):
    __tablename__ = 'policy_documents'
    document_id: Mapped[int] = mapped_column(ForeignKey('financial_documents.id'), primary_key=True)
    policy_version_id: Mapped[int] = mapped_column(ForeignKey('policy_versions.id'), index=True)
    knowledge_source_id: Mapped[int] = mapped_column(ForeignKey('knowledge_sources.id'), unique=True)
    source = relationship('KnowledgeSource')
    version = relationship('PolicyVersion')


class DocumentPermission(Base):
    __tablename__ = 'document_permissions'
    document_id: Mapped[int] = mapped_column(ForeignKey('financial_documents.id'), primary_key=True)
    role_name: Mapped[str] = mapped_column(ForeignKey('roles.name'), primary_key=True)


class EligibilityCriterion(Row):
    __tablename__ = 'eligibility_criteria'
    policy_version_id: Mapped[int] = mapped_column(ForeignKey('policy_versions.id'), index=True)
    key: Mapped[str]
    label: Mapped[str]
    operator: Mapped[str]
    threshold: Mapped[float]
    document_page_id: Mapped[int] = mapped_column(ForeignKey('document_pages.id'))
    quote: Mapped[str] = mapped_column(Text)
    source_page = relationship('DocumentPage')
    __table_args__ = (UniqueConstraint('policy_version_id', 'key'), CheckConstraint("operator IN ('min','max')", name='ck_criterion_operator'), CheckConstraint('threshold >= 0', name='ck_criterion_threshold'))


class EligibilityCriterionResult(Row):
    __tablename__ = 'eligibility_criterion_results'
    assessment_id: Mapped[int] = mapped_column(ForeignKey('eligibility_assessments.id'), index=True)
    criterion_id: Mapped[int] = mapped_column(ForeignKey('eligibility_criteria.id'))
    observed_value: Mapped[float | None]
    status: Mapped[str]
    evidence_valid: Mapped[bool]
    __table_args__ = (UniqueConstraint('assessment_id', 'criterion_id'), CheckConstraint("status IN ('SATISFIED','NOT_SATISFIED','UNKNOWN','CONFLICTING','NEEDS_HUMAN_REVIEW')", name='ck_criterion_status'))


class FinancialFeature(Row):
    __tablename__ = 'financial_features'
    assessment_id: Mapped[int] = mapped_column(ForeignKey('eligibility_assessments.id'), index=True)
    name: Mapped[str]
    value: Mapped[float | None]
    unit: Mapped[str]
    __table_args__ = (UniqueConstraint('assessment_id', 'name'),)


class MLModel(Row):
    __tablename__ = 'ml_models'
    name: Mapped[str] = mapped_column(unique=True)


class ModelVersion(Row):
    __tablename__ = 'model_versions'
    model_id: Mapped[int] = mapped_column(ForeignKey('ml_models.id'), index=True)
    version: Mapped[str]
    synthetic: Mapped[bool] = mapped_column(default=True)
    artifact_path: Mapped[str | None]
    __table_args__ = (UniqueConstraint('model_id', 'version'),)


class ModelPrediction(Row):
    __tablename__ = 'model_predictions'
    application_id: Mapped[int] = mapped_column(ForeignKey('loan_applications.id'), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey('eligibility_assessments.id'), index=True)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey('model_versions.id'))
    score: Mapped[float | None]
    category: Mapped[str]
    synthetic_model: Mapped[bool] = mapped_column(default=True)


class PredictionFeature(Row):
    __tablename__ = 'prediction_features'
    prediction_id: Mapped[int] = mapped_column(ForeignKey('model_predictions.id'), index=True)
    name: Mapped[str]
    value: Mapped[float | None]
    missing: Mapped[bool]
    __table_args__ = (UniqueConstraint('prediction_id', 'name'),)


class ModelEvaluation(Row):
    __tablename__ = 'model_evaluations'
    model_version_id: Mapped[int] = mapped_column(ForeignKey('model_versions.id'), index=True)
    split: Mapped[str]
    metric: Mapped[str]
    value: Mapped[float]
    __table_args__ = (UniqueConstraint('model_version_id', 'split', 'metric'),)


class CalibrationBin(Row):
    __tablename__ = 'calibration_bins'
    model_version_id: Mapped[int] = mapped_column(ForeignKey('model_versions.id'), index=True)
    split: Mapped[str]
    ordinal: Mapped[int]
    predicted: Mapped[float]
    observed: Mapped[float]
    __table_args__ = (UniqueConstraint('model_version_id', 'split', 'ordinal'),)


class ShapExplanation(Row):
    __tablename__ = 'shap_explanations'
    prediction_id: Mapped[int] = mapped_column(ForeignKey('model_predictions.id'), unique=True)
    baseline: Mapped[float]
    units: Mapped[str]


class ShapContribution(Row):
    __tablename__ = 'shap_contributions'
    explanation_id: Mapped[int] = mapped_column(ForeignKey('shap_explanations.id'), index=True)
    prediction_feature_id: Mapped[int] = mapped_column(ForeignKey('prediction_features.id'))
    value: Mapped[float]
    __table_args__ = (UniqueConstraint('explanation_id', 'prediction_feature_id'),)


class RetrievedEvidence(Row):
    __tablename__ = 'retrieved_evidence'
    query_id: Mapped[int | None] = mapped_column(ForeignKey('rag_queries.id'), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey('eligibility_assessments.id'), index=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey('document_chunks.id'), index=True)
    rank: Mapped[int]
    score: Mapped[float]
    __table_args__ = (CheckConstraint('(query_id IS NOT NULL AND assessment_id IS NULL) OR (query_id IS NULL AND assessment_id IS NOT NULL)', name='ck_evidence_context'),)


class GeneratedResponse(Row):
    __tablename__ = 'generated_responses'
    query_id: Mapped[int] = mapped_column(ForeignKey('rag_queries.id'), unique=True)
    text: Mapped[str] = mapped_column(Text)
    mode: Mapped[str]
    unsupported_claims: Mapped[int]


class ReviewerComment(Row):
    __tablename__ = 'reviewer_comments'
    review_id: Mapped[int] = mapped_column(ForeignKey('human_reviews.id'), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    text: Mapped[str] = mapped_column(Text)


class FairnessEvaluation(Row):
    __tablename__ = 'fairness_evaluations'
    model_version_id: Mapped[int] = mapped_column(ForeignKey('model_versions.id'), index=True)
    dataset_reference: Mapped[str]
    governance_reference: Mapped[str]
    metric: Mapped[str]
    group_reference: Mapped[str | None]
    value: Mapped[float | None]
    limitations: Mapped[str] = mapped_column(Text)


class ApplicationFeedback(Row):
    __tablename__ = 'application_feedback'
    application_id: Mapped[int] = mapped_column(ForeignKey('loan_applications.id'), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    text: Mapped[str] = mapped_column(Text)


class MigrationIssue(Row):
    __tablename__ = 'migration_issues'
    entity_type: Mapped[str]
    entity_id: Mapped[int]
    message: Mapped[str] = mapped_column(Text)


Application.profile_record = relationship(ApplicantProfile, back_populates='application', uselist=False, cascade='all, delete-orphan', lazy='selectin')
Product.active_version_id = mapped_column(ForeignKey('policy_versions.id', use_alter=True, name='fk_product_active_version'), nullable=True)
Product.active_version = relationship(PolicyVersion, foreign_keys=[Product.active_version_id], post_update=True)
Product.versions = relationship(PolicyVersion, foreign_keys=[PolicyVersion.product_id], back_populates='product', cascade='all, delete-orphan')
Document.page_records = relationship(DocumentPage, back_populates='document', cascade='all, delete-orphan', order_by=DocumentPage.id, lazy='selectin')
Document.entity_records = property(lambda self: sorted([entity for page in self.page_records for entity in page.entities], key=lambda entity: entity.ordinal))
Document.warning_records = relationship(DocumentWarning, cascade='all, delete-orphan', lazy='selectin')
Document.source_record = relationship(KnowledgeSource, cascade='all, delete-orphan', uselist=False)
Document.policy_record = relationship(PolicyDocument, cascade='all, delete-orphan', uselist=False)
Document.permission_records = relationship(DocumentPermission, cascade='all, delete-orphan')
Review.comment_records = relationship(ReviewerComment, cascade='all, delete-orphan', order_by=ReviewerComment.id)
RagQuery.generated_record = relationship(GeneratedResponse, cascade='all, delete-orphan', uselist=False)
RagQuery.evidence_records = relationship(RetrievedEvidence, cascade='all, delete-orphan')
Document.extraction_method = mapped_column(String, default='text extraction')
Document.extraction_confidence = mapped_column(Float, nullable=True)
Document.extraction_verified = mapped_column(Boolean, default=False)
Document.quarantined = mapped_column(Boolean, default=False)
Chunk.active = mapped_column(Boolean, default=True)
Chunk.document_page_id = mapped_column(ForeignKey('document_pages.id'),nullable=False,index=True)
Chunk.source_page = relationship(DocumentPage)


def chunk_document(self):
    return self.source_page.document_id


def chunk_document_expression(cls):
    return select(DocumentPage.document_id).where(DocumentPage.id==cls.document_page_id).correlate_except(DocumentPage).scalar_subquery()


def chunk_page(self):
    return self.source_page.page_number


def chunk_page_expression(cls):
    return select(DocumentPage.page_number).where(DocumentPage.id==cls.document_page_id).correlate_except(DocumentPage).scalar_subquery()


Chunk.document_id = hybrid_property(chunk_document).expression(chunk_document_expression)
Chunk.page = hybrid_property(chunk_page).expression(chunk_page_expression)

# Properties translate API DTOs to typed relational rows; they are not JSON storage.
from .normalized_access import profile_get, profile_set, policy_name_get, policy_name_set, jurisdiction_get, jurisdiction_set, criteria_get, criteria_set, pages_get, pages_set, extraction_get, extraction_set
Application.profile = property(profile_get, profile_set)
Product.policy_version = property(policy_name_get, policy_name_set)
Product.jurisdiction = property(jurisdiction_get, jurisdiction_set)
Product.criteria = property(criteria_get, criteria_set)
Document.pages = property(pages_get, pages_set)
Document.extraction = property(extraction_get, extraction_set)
