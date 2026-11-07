"""Initial LoanWise schema. Immutable migration snapshot is stored in schema_v1.py."""
from alembic import op
from app.schema_v1 import metadata

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    metadata.drop_all(op.get_bind())
