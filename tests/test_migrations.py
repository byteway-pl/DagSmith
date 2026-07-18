from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa

from dagsmith.core.db import Draft, DraftVersion, session_scope
from dagsmith.core.migrate import VERSION_TABLE, run_migrations


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'dagsmith.db'}"


def test_upgrade_creates_tables(tmp_path: Path) -> None:
    url = _sqlite_url(tmp_path)
    run_migrations("upgrade", "head", url=url)

    inspector = sa.inspect(sa.create_engine(url))
    tables = set(inspector.get_table_names())
    assert {"dagsmith_draft", "dagsmith_draft_version", VERSION_TABLE} <= tables


def test_downgrade_removes_tables(tmp_path: Path) -> None:
    url = _sqlite_url(tmp_path)
    run_migrations("upgrade", "head", url=url)
    run_migrations("downgrade", "base", url=url)

    inspector = sa.inspect(sa.create_engine(url))
    tables = set(inspector.get_table_names())
    assert "dagsmith_draft" not in tables
    assert "dagsmith_draft_version" not in tables


def test_models_roundtrip_on_migrated_schema(tmp_path: Path) -> None:
    url = _sqlite_url(tmp_path)
    run_migrations("upgrade", "head", url=url)

    with session_scope(url=url) as session:
        draft = Draft(bundle="dags-folder", rel_path="etl/my_dag.py", head_version_no=1)
        session.add(draft)
        session.flush()
        session.add(
            DraftVersion(
                draft_id=draft.id,
                version_no=1,
                source="# dagsmith: v1\n",
                layout={"nodes": {"extract": {"x": 0, "y": 0}}},
                kind="manual",
                message="initial",
            )
        )

    with session_scope(url=url) as session:
        loaded = session.query(Draft).one()
        assert loaded.rel_path == "etl/my_dag.py"
        assert loaded.versions[0].layout == {"nodes": {"extract": {"x": 0, "y": 0}}}
        assert loaded.versions[0].kind == "manual"
