"""End-to-end API tests of the draft -> save -> validate -> deploy cycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from dagsmith.core import validation


@pytest.fixture(autouse=True)
def _fast_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deep validation needs Airflow (subprocess); stub it as OK in unit tests."""
    monkeypatch.setattr(
        validation,
        "check_import",
        lambda source: ([], 1),
    )


def _create_draft(api_client, rel_path: str = "etl/my_dag.py") -> dict:
    response = api_client.post(
        "/api/v1/drafts", json={"bundle": "test", "rel_path": rel_path}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_draft_from_template(api_client) -> None:
    draft = _create_draft(api_client)
    assert draft["head_version_no"] == 1
    assert draft["base_file_hash"] is None
    assert draft["source"].startswith("# dagsmith: v1")
    assert "def my_dag():" in draft["source"]
    assert draft["live_file_hash"] is None


def test_create_draft_from_live_file(api_client, bundle_dir: Path) -> None:
    (bundle_dir / "existing.py").write_text("# existing dag\n")
    draft = _create_draft(api_client, "existing.py")
    assert draft["source"] == "# existing dag\n"
    assert draft["base_file_hash"] is not None
    assert draft["live_conflict"] is False


def test_open_existing_draft_is_idempotent(api_client) -> None:
    first = _create_draft(api_client, "same.py")
    second = _create_draft(api_client, "same.py")
    assert first["id"] == second["id"]


def test_save_version_and_conflict(api_client) -> None:
    draft = _create_draft(api_client, "versioned.py")
    response = api_client.put(
        f"/api/v1/drafts/{draft['id']}/versions",
        json={"source": "x = 2\n", "expected_head_version_no": 1, "message": "second"},
    )
    assert response.status_code == 200
    assert response.json()["version_no"] == 2

    stale = api_client.put(
        f"/api/v1/drafts/{draft['id']}/versions",
        json={"source": "x = 3\n", "expected_head_version_no": 1},
    )
    assert stale.status_code == 409
    body = stale.json()
    assert body["code"] == "conflict"
    assert body["detail"]["head_version_no"] == 2


def test_autosave_compaction(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRFLOW__DAGSMITH__AUTO_VERSIONS_KEEP", "3")
    draft = _create_draft(api_client, "autos.py")
    for i in range(6):
        response = api_client.put(
            f"/api/v1/drafts/{draft['id']}/versions",
            json={
                "source": f"x = {i}\n",
                "kind": "auto",
                "expected_head_version_no": 1 + i,
            },
        )
        assert response.status_code == 200
    versions = api_client.get(f"/api/v1/drafts/{draft['id']}/versions").json()
    autos = [v for v in versions if v["kind"] == "auto"]
    assert len(autos) == 3
    # manual initial version is never compacted away
    assert any(v["version_no"] == 1 for v in versions)


def test_history_and_restore(api_client) -> None:
    draft = _create_draft(api_client, "hist.py")
    api_client.put(
        f"/api/v1/drafts/{draft['id']}/versions",
        json={"source": "x = 2\n", "expected_head_version_no": 1},
    )
    old = api_client.get(f"/api/v1/drafts/{draft['id']}/versions/1").json()
    restored = api_client.post(f"/api/v1/drafts/{draft['id']}/restore/1")
    assert restored.status_code == 200
    head = api_client.get(f"/api/v1/drafts/{draft['id']}").json()
    assert head["head_version_no"] == 3
    assert head["source"] == old["source"]


def test_deploy_writes_file_and_handles_conflict(api_client, bundle_dir: Path) -> None:
    draft = _create_draft(api_client, "deployme.py")

    ok = api_client.post(
        f"/api/v1/drafts/{draft['id']}/deploy",
        json={"expected_file_hash": None},
    )
    assert ok.status_code == 200, ok.text
    deployed_hash = ok.json()["file_hash"]
    assert (bundle_dir / "deployme.py").read_text() == draft["source"]
    assert ok.json()["backup_path"] is None  # file did not exist before

    # someone edits the live file outside DagSmith
    (bundle_dir / "deployme.py").write_text("# rogue change\n")
    conflict = api_client.post(
        f"/api/v1/drafts/{draft['id']}/deploy",
        json={"expected_file_hash": deployed_hash},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["live_content"] == "# rogue change\n"

    # resolve: deploy on top of the current live hash, with backup this time
    current_hash = conflict.json()["detail"]["live_file_hash"]
    resolved = api_client.post(
        f"/api/v1/drafts/{draft['id']}/deploy",
        json={"expected_file_hash": current_hash},
    )
    assert resolved.status_code == 200
    assert resolved.json()["backup_path"] is not None
    assert (bundle_dir / "deployme.py").read_text() == draft["source"]


def test_deploy_blocked_by_validation(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    draft = _create_draft(api_client, "invalid.py")
    api_client.put(
        f"/api/v1/drafts/{draft['id']}/versions",
        json={"source": "def broken(:\n", "expected_head_version_no": 1},
    )
    response = api_client.post(
        f"/api/v1/drafts/{draft['id']}/deploy", json={"expected_file_hash": None}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert body["detail"]["errors"][0]["kind"] == "syntax"


def test_files_listing_marks_drafts(api_client, bundle_dir: Path) -> None:
    (bundle_dir / "plain.py").write_text("a = 1\n")
    (bundle_dir / "drafted.py").write_text("b = 2\n")
    _create_draft(api_client, "drafted.py")
    files = {f["rel_path"]: f for f in api_client.get("/api/v1/files?bundle=test").json()}
    assert files["drafted.py"]["has_draft"] is True
    assert files["plain.py"]["has_draft"] is False


def test_reload_from_bundle_file(api_client, bundle_dir: Path) -> None:
    (bundle_dir / "live.py").write_text("# deployed version\nx = 1\n")
    draft = _create_draft(api_client, "live.py")
    # edit the draft away from the live file
    api_client.put(
        f"/api/v1/drafts/{draft['id']}/versions",
        json={"source": "# WIP local edit\n", "expected_head_version_no": 1},
    )
    # someone deploys a newer version straight to disk
    (bundle_dir / "live.py").write_text("# newer prod\ny = 2\n")

    reloaded = api_client.post(f"/api/v1/drafts/{draft['id']}/reload")
    assert reloaded.status_code == 200, reloaded.text
    body = reloaded.json()
    assert body["source"] == "# newer prod\ny = 2\n"
    assert body["live_conflict"] is False  # back in sync with disk
    # it appended a version (didn't rewrite history)
    versions = api_client.get(f"/api/v1/drafts/{draft['id']}/versions").json()
    assert versions[0]["message"] == "loaded from bundle (deployed file)"


def test_reload_without_deployed_file_is_404(api_client) -> None:
    draft = _create_draft(api_client, "never_deployed.py")
    response = api_client.post(f"/api/v1/drafts/{draft['id']}/reload")
    assert response.status_code == 404


def test_validate_endpoint_syntax_only(api_client) -> None:
    response = api_client.post(
        "/api/v1/validate", json={"source": "x = (\n", "deep": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["errors"][0]["kind"] == "syntax"
    assert body["errors"][0]["line"] is not None


def test_unauthenticated_request_is_401(migrated_db: str) -> None:
    from fastapi.testclient import TestClient

    from dagsmith.api.app import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/drafts")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
