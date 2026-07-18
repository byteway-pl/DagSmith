from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Unit tests run without a configured Airflow: disable startup auto-migration
# and point both the DagSmith DB and AIRFLOW_HOME at throwaway locations
# before dagsmith modules are imported.
_TMP = tempfile.mkdtemp(prefix="dagsmith-tests-")
os.environ.setdefault("AIRFLOW__DAGSMITH__AUTO_MIGRATE", "False")
os.environ.setdefault("DAGSMITH_SQL_ALCHEMY_CONN", f"sqlite:///{_TMP}/dagsmith.db")
os.environ.setdefault("AIRFLOW_HOME", f"{_TMP}/airflow_home")


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """Apply migrations once to the session-wide sqlite DB used by get_engine()."""
    from dagsmith.core.migrate import run_migrations

    url = os.environ["DAGSMITH_SQL_ALCHEMY_CONN"]
    run_migrations("upgrade", "head", url=url)
    return url


@pytest.fixture
def bundle_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake writable local bundle named 'test', patched into storage discovery."""
    from dagsmith.core import storage

    root = tmp_path / "dags"
    root.mkdir()

    def fake_list_bundles() -> list[storage.BundleRef]:
        return [storage.BundleRef(name="test", root=root.resolve(), writable=True)]

    monkeypatch.setattr(storage, "list_bundles", fake_list_bundles)
    return root


@pytest.fixture
def api_client(migrated_db: str, bundle_dir: Path) -> Iterator[object]:
    """TestClient with auth dependencies overridden (user 'tester', full rights)."""
    from fastapi.testclient import TestClient

    from dagsmith.api import security
    from dagsmith.api.app import create_app

    app = create_app()
    user = security.ApiUser(username="tester", airflow_user=object())
    for dep in (
        security.get_current_user,
        security.require_read,
        security.require_edit,
        security.require_deploy,
    ):
        app.dependency_overrides[dep] = lambda: user

    with TestClient(app) as client:
        yield client
