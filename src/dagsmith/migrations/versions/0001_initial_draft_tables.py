"""Initial DagSmith tables: dagsmith_draft, dagsmith_draft_version.

Revision ID: 0001
Revises:
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "dagsmith_draft",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bundle", sa.String(250), nullable=False),
        sa.Column("rel_path", sa.String(1000), nullable=False),
        sa.Column("base_file_hash", sa.String(64), nullable=True),
        sa.Column("head_version_no", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(250), nullable=True),
        sa.Column("updated_by", sa.String(250), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("bundle", "rel_path", name="uq_dagsmith_draft_bundle_rel_path"),
    )
    op.create_index("ix_dagsmith_draft_status", "dagsmith_draft", ["status"])

    op.create_table(
        "dagsmith_draft_version",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "draft_id",
            sa.String(36),
            sa.ForeignKey("dagsmith_draft.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("layout", JSONType, nullable=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("created_by", sa.String(250), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("draft_id", "version_no", name="uq_dagsmith_draft_version_no"),
    )
    op.create_index(
        "ix_dagsmith_draft_version_draft_id", "dagsmith_draft_version", ["draft_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_dagsmith_draft_version_draft_id", table_name="dagsmith_draft_version")
    op.drop_table("dagsmith_draft_version")
    op.drop_index("ix_dagsmith_draft_status", table_name="dagsmith_draft")
    op.drop_table("dagsmith_draft")
