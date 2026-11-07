"""Durable database-backed originals for serverless deployments."""
from alembic import op
import sqlalchemy as sa

revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('financial_documents',sa.Column('content_bytes',sa.LargeBinary(),nullable=True))

def downgrade():
    raise RuntimeError('Restore a backup rather than discarding uploaded document originals.')
