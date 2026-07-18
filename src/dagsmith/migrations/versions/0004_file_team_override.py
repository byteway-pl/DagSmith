"""Per-file team override: dagsmith_file_team.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dagsmith_file_team",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bundle", sa.String(250), nullable=False),
        sa.Column("rel_path", sa.String(1000), nullable=False),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("dagsmith_team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assigned_by", sa.String(250), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("bundle", "rel_path", name="uq_dagsmith_file_team_path"),
    )


def downgrade() -> None:
    op.drop_table("dagsmith_file_team")
