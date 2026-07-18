"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import orm

from dagsmith.core.db import session_scope


def db_session() -> Iterator[orm.Session]:
    with session_scope() as session:
        yield session
