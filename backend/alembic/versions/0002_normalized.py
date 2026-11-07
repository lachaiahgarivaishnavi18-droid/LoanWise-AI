"""Normalize operational facts and backfill revision 0001 without discarding history."""
import json
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import op
from app.schema_v2 import metadata

revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None


def decode(value):
    return json.loads(value) if isinstance(value,str) else value


def upgrade():
    connection=op.get_bind()
    products=connection.execute(sa.text('SELECT id, policy_version, jurisdiction, criteria FROM loan_products')).mappings().all()
    applications=connection.execute(sa.text('SELECT id, profile FROM loan_applications')).mappings().all()
    documents=connection.execute(sa.text('SELECT id, pages, extraction FROM financial_documents')).mappings().all()
    chunks=connection.execute(sa.text('SELECT id, document_id, page FROM document_chunks')).mappings().all()
    op.add_column('loan_products',sa.Column('active_version_id',sa.Integer(),nullable=True))
    op.add_column('financial_documents',sa.Column('extraction_method',sa.String(),nullable=True))
    op.add_column('financial_documents',sa.Column('extraction_confidence',sa.Float(),nullable=True))
    op.add_column('financial_documents',sa.Column('extraction_verified',sa.Boolean(),nullable=True,server_default=sa.false()))
    op.add_column('financial_documents',sa.Column('quarantined',sa.Boolean(),nullable=True,server_default=sa.false()))
    op.add_column('document_chunks',sa.Column('active',sa.Boolean(),nullable=True,server_default=sa.true()))
    op.add_column('document_chunks',sa.Column('document_page_id',sa.Integer(),nullable=True))
    metadata.create_all(connection)
    from app.models import Product, Application, Document, Assessment, RagQuery, Review, Chunk
    from app.normalized_models import GeneratedResponse, RetrievedEvidence, ReviewerComment, MigrationIssue, DocumentPage
    from app.normalized_services import initialize_roles, catalog_document, persist_assessment
    with Session(bind=connection) as db:
        initialize_roles(db)
        for row in products:
            product=db.get(Product,row['id'])
            product.policy_version=row['policy_version']
            product.jurisdiction=row['jurisdiction']
        db.flush()
        for row in applications:
            db.get(Application,row['id']).profile=decode(row['profile'])
        for row in documents:
            document=db.get(Document,row['id'])
            document.pages=decode(row['pages'])
            document.extraction=decode(row['extraction'])
            catalog_document(db,document)
        db.flush()
        for row in chunks:
            page=db.scalar(sa.select(DocumentPage).where(DocumentPage.document_id==row['document_id'],DocumentPage.page_number==row['page'],DocumentPage.active==True))
            if page is None:
                raise RuntimeError('Legacy chunk has no recoverable source page; upgrade withheld rather than fabricating provenance')
            db.get(Chunk,row['id']).source_page=page
        db.flush()
        for row in products:
            db.get(Product,row['id']).criteria=decode(row['criteria'])
        db.flush()
        for record in db.scalars(sa.select(Assessment)).all():
            persist_assessment(db,record,strict=False)
        for query in db.scalars(sa.select(RagQuery)).all():
            response=query.response
            query.generated_record=GeneratedResponse(text=response['answer'],mode=response['mode'],unsupported_claims=response.get('unsupported_claims',0),created_at=query.created_at)
            for i,evidence in enumerate(response.get('evidence',[])):
                if db.get(Chunk,evidence['chunk_id']):
                    query.evidence_records.append(RetrievedEvidence(chunk_id=evidence['chunk_id'],rank=i+1,score=evidence['score'],created_at=query.created_at))
                else:
                    db.add(MigrationIssue(entity_type='rag_query',entity_id=query.id,message='Original citation chunk was removed before normalization; original response snapshot retained.'))
        for review in db.scalars(sa.select(Review)).all():
            review.comment_records.append(ReviewerComment(reviewer_id=review.reviewer_id,text=review.comment,created_at=review.created_at))
        db.flush()
        # The outer Alembic transaction owns commit/rollback.
    op.drop_index('ix_document_chunks_document_id',table_name='document_chunks')
    for table,columns in [('loan_applications',['profile']),('loan_products',['policy_version','jurisdiction','criteria']),('financial_documents',['pages','extraction']),('document_chunks',['document_id','page'])]:
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.drop_column(column)
    with op.batch_alter_table('users') as batch:
        batch.create_foreign_key('fk_user_role','roles',['role'],['name'])
    with op.batch_alter_table('loan_products') as batch:
        batch.create_foreign_key('fk_product_active_version','policy_versions',['active_version_id'],['id'])
    with op.batch_alter_table('document_chunks') as batch:
        batch.alter_column('document_page_id',existing_type=sa.Integer(),nullable=False)
        batch.create_foreign_key('fk_chunk_source_page','document_pages',['document_page_id'],['id'])
        batch.create_index('ix_document_chunks_document_page_id',['document_page_id'])
    with op.batch_alter_table('loan_applications') as batch:
        batch.alter_column('amount',existing_type=sa.Float(),type_=sa.Numeric(18,2),nullable=False)
        batch.alter_column('annual_rate',existing_type=sa.Float(),type_=sa.Numeric(7,4),nullable=True)
        batch.create_check_constraint('ck_application_amount','amount > 0')
        batch.create_check_constraint('ck_application_tenure','tenure_months BETWEEN 1 AND 600')
        batch.create_check_constraint('ck_application_rate','annual_rate IS NULL OR annual_rate BETWEEN 0 AND 100')
    with op.batch_alter_table('financial_documents') as batch:
        batch.create_check_constraint('ck_document_scope',"(kind = 'policy' AND product_id IS NOT NULL AND application_id IS NULL) OR (kind = 'financial' AND application_id IS NOT NULL AND product_id IS NULL)")
    with op.batch_alter_table('human_reviews') as batch:
        batch.create_check_constraint('ck_review_status',"status IN ('REVIEWED','MORE_INFORMATION_REQUIRED')")
    with op.batch_alter_table('final_human_decisions') as batch:
        batch.create_check_constraint('ck_human_decision',"decision IN ('APPROVED','REJECTED','DEFERRED')")
    if connection.dialect.name=='sqlite' and connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('Foreign-key validation failed; normalization transaction was rolled back')


def downgrade():
    raise RuntimeError('Normalization preserves append-only source history. Restore a pre-upgrade backup instead of a lossy downgrade.')
