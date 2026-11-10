"""Persist personal DAG templates."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dagsmith_template",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(250), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
    )
    op.create_index("ix_dagsmith_template_owner", "dagsmith_template", ["owner"])


def downgrade():
    op.drop_table("dagsmith_template")
