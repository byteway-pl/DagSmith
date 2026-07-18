"""Teams: dagsmith_team, dagsmith_team_member.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dagsmith_team",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("bundle", sa.String(250), nullable=False),
        sa.Column("path_prefix", sa.String(500), nullable=False),
        sa.Column("git_push", sa.Boolean, nullable=False),
        sa.Column("created_by", sa.String(250), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "dagsmith_team_member",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("dagsmith_team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("username", sa.String(250), nullable=False),
        sa.UniqueConstraint("team_id", "username", name="uq_dagsmith_team_member"),
    )
    op.create_index(
        "ix_dagsmith_team_member_username", "dagsmith_team_member", ["username"]
    )


def downgrade() -> None:
    op.drop_index("ix_dagsmith_team_member_username", table_name="dagsmith_team_member")
    op.drop_table("dagsmith_team_member")
    op.drop_table("dagsmith_team")
