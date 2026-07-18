"""SQLAlchemy models for DagSmith tables (``dagsmith_`` prefix) and session helpers.

DagSmith owns its tables in the Airflow metadata database: independent metadata,
independent Alembic chain, no foreign keys to Airflow tables, own sessions.
Column types stay portable (JSON with a JSONB variant on Postgres, string UUIDs)
so the unit-test suite can run on SQLite while production runs on Postgres.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()
Base = orm.declarative_base(metadata=metadata)

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

DRAFT_STATUSES = ("active", "deployed", "archived")
VERSION_KINDS = ("auto", "manual", "deploy")


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Draft(Base):
    __tablename__ = "dagsmith_draft"

    id = sa.Column(sa.String(36), primary_key=True, default=_new_uuid)
    bundle = sa.Column(sa.String(250), nullable=False)
    rel_path = sa.Column(sa.String(1000), nullable=False)
    # SHA-256 of the live file content this draft was branched from; NULL = new file.
    base_file_hash = sa.Column(sa.String(64), nullable=True)
    head_version_no = sa.Column(sa.Integer, nullable=False, default=0)
    status = sa.Column(sa.String(16), nullable=False, default="active")
    created_by = sa.Column(sa.String(250), nullable=True)
    updated_by = sa.Column(sa.String(250), nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    versions = orm.relationship(
        "DraftVersion", back_populates="draft", cascade="all, delete-orphan"
    )

    __table_args__ = (
        sa.UniqueConstraint("bundle", "rel_path", name="uq_dagsmith_draft_bundle_rel_path"),
        sa.Index("ix_dagsmith_draft_status", "status"),
    )


class DraftVersion(Base):
    __tablename__ = "dagsmith_draft_version"

    id = sa.Column(sa.String(36), primary_key=True, default=_new_uuid)
    draft_id = sa.Column(
        sa.String(36),
        sa.ForeignKey("dagsmith_draft.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no = sa.Column(sa.Integer, nullable=False)
    source = sa.Column(sa.Text, nullable=False)
    # Canvas projection (node positions, zoom); NULL = auto-layout on the frontend.
    layout = sa.Column(JSONType, nullable=True)
    kind = sa.Column(sa.String(8), nullable=False, default="manual")
    message = sa.Column(sa.String(500), nullable=True)
    created_by = sa.Column(sa.String(250), nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=_utcnow)
    deployed_at = sa.Column(sa.DateTime(timezone=True), nullable=True)

    draft = orm.relationship("Draft", back_populates="versions")

    __table_args__ = (
        sa.UniqueConstraint("draft_id", "version_no", name="uq_dagsmith_draft_version_no"),
        sa.Index("ix_dagsmith_draft_version_draft_id", "draft_id"),
    )


class Team(Base):
    """A DagSmith team: owns a directory prefix inside a bundle (its git checkout)."""

    __tablename__ = "dagsmith_team"

    id = sa.Column(sa.String(36), primary_key=True, default=_new_uuid)
    name = sa.Column(sa.String(100), nullable=False, unique=True)
    description = sa.Column(sa.String(500), nullable=True)
    bundle = sa.Column(sa.String(250), nullable=False)
    # Directory prefix inside the bundle owned by the team ("" = whole bundle).
    path_prefix = sa.Column(sa.String(500), nullable=False, default="")
    # Team repository: pushes go to this remote/branch (None = checkout's origin).
    git_remote_url = sa.Column(sa.String(500), nullable=True)
    git_branch = sa.Column(sa.String(200), nullable=False, default="main")
    # Auto commit & push to the team repo after every deploy.
    git_push = sa.Column(sa.Boolean, nullable=False, default=False)
    created_by = sa.Column(sa.String(250), nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=_utcnow)

    members = orm.relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    file_overrides = orm.relationship(
        "FileTeam", back_populates="team", cascade="all, delete-orphan"
    )


class FileTeam(Base):
    """Admin-set override: this file belongs to that team, regardless of its
    directory. Wins over the team path-prefix match."""

    __tablename__ = "dagsmith_file_team"

    id = sa.Column(sa.String(36), primary_key=True, default=_new_uuid)
    bundle = sa.Column(sa.String(250), nullable=False)
    rel_path = sa.Column(sa.String(1000), nullable=False)
    team_id = sa.Column(
        sa.String(36), sa.ForeignKey("dagsmith_team.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by = sa.Column(sa.String(250), nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=_utcnow)

    team = orm.relationship("Team", back_populates="file_overrides")

    __table_args__ = (
        sa.UniqueConstraint("bundle", "rel_path", name="uq_dagsmith_file_team_path"),
    )


class TeamMember(Base):
    __tablename__ = "dagsmith_team_member"

    id = sa.Column(sa.String(36), primary_key=True, default=_new_uuid)
    team_id = sa.Column(
        sa.String(36), sa.ForeignKey("dagsmith_team.id", ondelete="CASCADE"), nullable=False
    )
    username = sa.Column(sa.String(250), nullable=False)

    team = orm.relationship("Team", back_populates="members")

    __table_args__ = (
        sa.UniqueConstraint("team_id", "username", name="uq_dagsmith_team_member"),
        sa.Index("ix_dagsmith_team_member_username", "username"),
    )


_engine: sa.engine.Engine | None = None


def get_engine(url: str | None = None) -> sa.engine.Engine:
    """Process-wide engine; explicit ``url`` bypasses the cache (CLI, tests)."""
    global _engine
    if url is not None:
        return sa.create_engine(url, future=True)
    if _engine is None:
        from dagsmith.config import sql_alchemy_url

        _engine = sa.create_engine(sql_alchemy_url(), future=True)
    return _engine


@contextmanager
def session_scope(url: str | None = None) -> Iterator[orm.Session]:
    session = orm.Session(bind=get_engine(url), future=True)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
