"""Git-on-deploy integration and the audit endpoint."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dagsmith.core import gitops, validation
from dagsmith.core.storage import BundleRef


@pytest.fixture(autouse=True)
def _fast_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "check_import", lambda source: ([], 1))


def _git_bundle(tmp_path: Path) -> BundleRef:
    root = tmp_path / "gitdags"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    return BundleRef(name="test", root=root.resolve(), writable=True)


def test_is_git_repo(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert gitops.is_git_repo(BundleRef(name="p", root=plain, writable=True)) is False
    assert gitops.is_git_repo(_git_bundle(tmp_path)) is True


def test_commit_deploy_creates_commit(tmp_path: Path) -> None:
    bundle = _git_bundle(tmp_path)
    (bundle.root / "dag.py").write_text("x = 1\n")
    result = gitops.commit_deploy(bundle, "dag.py", "alice", "dagsmith: deploy dag.py", push=False)
    assert result.error is None
    assert result.commit_sha is not None
    log_proc = subprocess.run(
        ["git", "-C", str(bundle.root), "log", "-1", "--format=%an|%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert log_proc.stdout.strip() == "alice|dagsmith: deploy dag.py"


def test_commit_deploy_nothing_to_commit(tmp_path: Path) -> None:
    bundle = _git_bundle(tmp_path)
    (bundle.root / "dag.py").write_text("x = 1\n")
    first = gitops.commit_deploy(bundle, "dag.py", "alice", "first", push=False)
    result = gitops.commit_deploy(bundle, "dag.py", "alice", "second", push=False)
    assert result.error is None
    # no new commit — HEAD (the first commit) is reported so a push knows what went out
    assert result.commit_sha == first.commit_sha


def test_deploy_with_git_and_audit_endpoint(
    api_client, bundle_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIRFLOW__DAGSMITH__GIT_COMMIT", "True")
    subprocess.run(["git", "init", "-q", "-b", "main", str(bundle_dir)], check=True)

    draft = api_client.post(
        "/api/v1/drafts", json={"bundle": "test", "rel_path": "gitted.py"}
    ).json()
    response = api_client.post(
        f"/api/v1/drafts/{draft['id']}/deploy", json={"expected_file_hash": None}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["git_commit_sha"] is not None
    assert body["git_error"] is None
    assert body["git_pushed"] is False

    entries = api_client.get("/api/v1/audit").json()
    assert entries, "audit log should not be empty"
    latest = entries[0]
    assert latest["action"] == "deploy"
    assert latest["rel_path"] == "gitted.py"
    assert latest["git_commit_sha"] == body["git_commit_sha"]

    # bundle listing reports the git flag
    bundles = api_client.get("/api/v1/bundles").json()
    assert bundles[0]["git"] is True
