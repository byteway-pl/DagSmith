"""Team git target: remote URL + branch.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dagsmith_team", sa.Column("git_remote_url", sa.String(500), nullable=True)
    )
    op.add_column(
        "dagsmith_team",
        sa.Column("git_branch", sa.String(200), nullable=False, server_default="main"),
    )


def downgrade() -> None:
    op.drop_column("dagsmith_team", "git_branch")
    op.drop_column("dagsmith_team", "git_remote_url")
