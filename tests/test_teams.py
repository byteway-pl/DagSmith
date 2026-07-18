"""Teams: CRUD, path ownership enforcement, git push endpoint, team tag."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from dagsmith.core import validation


@pytest.fixture(autouse=True)
def _fast_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "check_import", lambda source: ([], 1))


@pytest.fixture
def two_user_clients(migrated_db: str, bundle_dir: Path) -> Iterator[tuple]:
    """(admin_client, alice_client, bob_client) — alice will be on the team."""
    from fastapi.testclient import TestClient

    from dagsmith.api import security
    from dagsmith.api.app import create_app

    def make(username: str, admin: bool):
        app = create_app()
        user = security.ApiUser(username=username, airflow_user=object())
        app.dependency_overrides[security.get_current_user] = lambda: user
        app.dependency_overrides[security.require_read] = lambda: user
        app.dependency_overrides[security.require_edit] = lambda: user
        app.dependency_overrides[security.require_deploy] = lambda: user
        if admin:
            app.dependency_overrides[security.require_admin] = lambda: user
        # is_admin() is called directly (not via Depends) — patch per request
        return app, user

    admin_app, admin_user = make("boss", admin=True)
    alice_app, _ = make("alice", admin=False)
    bob_app, _ = make("bob", admin=False)

    import dagsmith.api.routes.drafts as drafts_routes
    import dagsmith.api.routes.files as files_routes

    admins = {"boss"}
    fake_is_admin = lambda user: user.username in admins  # noqa: E731
    for module in (drafts_routes, files_routes):
        original = module.is_admin
        module.is_admin = fake_is_admin  # type: ignore[assignment]
    try:
        with TestClient(admin_app) as admin_client, TestClient(alice_app) as alice_client, \
                TestClient(bob_app) as bob_client:
            # the session-wide sqlite DB is shared across tests — start clean
            for team in admin_client.get("/api/v1/teams").json():
                admin_client.delete(f"/api/v1/teams/{team['id']}")
            yield admin_client, alice_client, bob_client
    finally:
        for module in (drafts_routes, files_routes):
            module.is_admin = original  # type: ignore[assignment]


def _mk_team(admin_client, **overrides) -> dict:
    body = {
        "name": "data-team",
        "bundle": "test",
        "path_prefix": "data",
        "git_push": False,
        "description": "ETL crew",
    }
    body.update(overrides)
    response = admin_client.post("/api/v1/teams", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_team_crud_and_members(two_user_clients) -> None:
    admin_client, alice_client, _bob = two_user_clients
    team = _mk_team(admin_client)
    assert admin_client.post(f"/api/v1/teams/{team['id']}/members/alice").status_code == 204

    teams = alice_client.get("/api/v1/teams").json()
    assert teams[0]["name"] == "data-team"
    assert teams[0]["members"] == ["alice"]

    # non-admin cannot manage teams
    denied = alice_client.post(
        "/api/v1/teams", json={"name": "x", "bundle": "test", "path_prefix": ""}
    )
    assert denied.status_code == 403

    assert (
        admin_client.delete(f"/api/v1/teams/{team['id']}/members/alice").status_code == 204
    )
    assert admin_client.get("/api/v1/teams").json()[0]["members"] == []


def test_team_ownership_enforced(two_user_clients, bundle_dir: Path) -> None:
    admin_client, alice_client, bob_client = two_user_clients
    team = _mk_team(admin_client)
    admin_client.post(f"/api/v1/teams/{team['id']}/members/alice")

    # member creates a DAG under the team prefix -> team tag in the template
    created = alice_client.post(
        "/api/v1/drafts", json={"bundle": "test", "rel_path": "data/etl_a.py"}
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert "tags=['team:data-team']" in draft["source"]

    # non-member cannot touch the team's file
    denied = bob_client.post(
        "/api/v1/drafts", json={"bundle": "test", "rel_path": "data/etl_a.py"}
    )
    assert denied.status_code == 403
    assert "data-team" in denied.json()["message"]

    denied_save = bob_client.put(
        f"/api/v1/drafts/{draft['id']}/versions",
        json={"source": "x = 1\n", "expected_head_version_no": 1},
    )
    assert denied_save.status_code == 403

    # admin bypasses, files outside the prefix stay open to everyone
    assert (
        admin_client.post(
            "/api/v1/drafts", json={"bundle": "test", "rel_path": "data/etl_b.py"}
        ).status_code
        == 201
    )
    assert (
        bob_client.post(
            "/api/v1/drafts", json={"bundle": "test", "rel_path": "misc/free.py"}
        ).status_code
        == 201
    )

    # files listing reports ownership + editability
    (bundle_dir / "data").mkdir(exist_ok=True)
    (bundle_dir / "data" / "seen.py").write_text("x = 1\n")
    files_for_bob = {
        f["rel_path"]: f for f in bob_client.get("/api/v1/files?bundle=test").json()
    }
    assert files_for_bob["data/seen.py"]["team"] == "data-team"
    assert files_for_bob["data/seen.py"]["editable"] is False
    files_for_alice = {
        f["rel_path"]: f for f in alice_client.get("/api/v1/files?bundle=test").json()
    }
    assert files_for_alice["data/seen.py"]["editable"] is True


def test_file_team_override(two_user_clients, bundle_dir: Path) -> None:
    admin_client, alice_client, bob_client = two_user_clients
    team_a = _mk_team(admin_client, name="team-a", path_prefix="a")
    team_b = _mk_team(admin_client, name="team-b", path_prefix="b")
    admin_client.post(f"/api/v1/teams/{team_a['id']}/members/alice")
    admin_client.post(f"/api/v1/teams/{team_b['id']}/members/bob")

    # file physically in team-a's directory
    (bundle_dir / "a").mkdir(exist_ok=True)
    (bundle_dir / "a" / "dag.py").write_text("x = 1\n")

    # by directory: alice can edit, bob cannot
    assert (
        alice_client.post(
            "/api/v1/drafts", json={"bundle": "test", "rel_path": "a/dag.py"}
        ).status_code
        == 201
    )
    assert (
        bob_client.put(
            "/api/v1/file-team",
            json={"bundle": "test", "rel_path": "a/dag.py", "team_id": team_b["id"]},
        ).status_code
        == 403
    )  # non-admin cannot reassign

    # admin reassigns the DAG to team-b — override wins over the directory
    result = admin_client.put(
        "/api/v1/file-team",
        json={"bundle": "test", "rel_path": "a/dag.py", "team_id": team_b["id"]},
    )
    assert result.status_code == 200
    assert result.json()["team"] == "team-b"

    files = {f["rel_path"]: f for f in bob_client.get("/api/v1/files?bundle=test").json()}
    assert files["a/dag.py"]["team"] == "team-b"
    assert files["a/dag.py"]["editable"] is True

    draft_id = bob_client.post(
        "/api/v1/drafts", json={"bundle": "test", "rel_path": "a/dag.py"}
    ).json()["id"]
    denied = alice_client.put(
        f"/api/v1/drafts/{draft_id}/versions",
        json={"source": "y = 2\n", "expected_head_version_no": 1},
    )
    assert denied.status_code == 403  # alice lost access despite the directory

    # clearing the override restores directory-based ownership
    cleared = admin_client.put(
        "/api/v1/file-team",
        json={"bundle": "test", "rel_path": "a/dag.py", "team_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["team"] is None
    files = {f["rel_path"]: f for f in alice_client.get("/api/v1/files?bundle=test").json()}
    assert files["a/dag.py"]["team"] == "team-a"

    # a team from another bundle is rejected
    other = _mk_team(admin_client, name="other-bundle", bundle="elsewhere", path_prefix="")
    bad = admin_client.put(
        "/api/v1/file-team",
        json={"bundle": "test", "rel_path": "a/dag.py", "team_id": other["id"]},
    )
    assert bad.status_code == 400


def test_git_push_endpoint(two_user_clients, bundle_dir: Path) -> None:
    admin_client, alice_client, _bob = two_user_clients
    team = _mk_team(admin_client, name="push-team", path_prefix="push")
    admin_client.post(f"/api/v1/teams/{team['id']}/members/alice")
    subprocess.run(["git", "init", "-q", "-b", "main", str(bundle_dir)], check=True)

    draft = alice_client.post(
        "/api/v1/drafts", json={"bundle": "test", "rel_path": "push/pipe.py"}
    ).json()
    deploy = alice_client.post(
        f"/api/v1/drafts/{draft['id']}/deploy", json={"expected_file_hash": None}
    )
    assert deploy.status_code == 200, deploy.text

    # a team without a repo override inherits the bundle checkout's upstream —
    # push fails gracefully here (the test repo has no remote), commit works
    result = alice_client.post(f"/api/v1/drafts/{draft['id']}/git-push").json()
    assert result["commit_sha"] is not None
    assert result["pushed"] is False
    assert "push failed" in (result["error"] or "")

    log = subprocess.run(
        ["git", "-C", str(bundle_dir), "log", "-1", "--format=%an %s"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip() == "alice dagsmith: update push/pipe.py (draft v1)"


def test_git_push_to_team_repo_and_branch(
    two_user_clients, bundle_dir: Path, tmp_path: Path
) -> None:
    """The team's configured repo URL + branch is the push target."""
    admin_client, alice_client, _bob = two_user_clients
    target = tmp_path / "central.git"
    subprocess.run(["git", "init", "-q", "--bare", str(target)], check=True)

    team = _mk_team(
        admin_client,
        name="central-team",
        path_prefix="central",
        git_remote_url=str(target),
        git_branch="releases",
    )
    admin_client.post(f"/api/v1/teams/{team['id']}/members/alice")
    subprocess.run(["git", "init", "-q", "-b", "main", str(bundle_dir)], check=True)

    draft = alice_client.post(
        "/api/v1/drafts", json={"bundle": "test", "rel_path": "central/report.py"}
    ).json()
    assert (
        alice_client.post(
            f"/api/v1/drafts/{draft['id']}/deploy", json={"expected_file_hash": None}
        ).status_code
        == 200
    )

    result = alice_client.post(f"/api/v1/drafts/{draft['id']}/git-push").json()
    assert result["error"] is None, result
    assert result["pushed"] is True
    assert result["commit_sha"] is not None

    # the bare repo received the commit on the configured branch
    log = subprocess.run(
        ["git", "-C", str(target), "log", "releases", "-1", "--format=%an %s"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "alice" in log.stdout
    assert "central/report.py" in log.stdout


def test_team_auto_push_on_deploy(
    two_user_clients, bundle_dir: Path, tmp_path: Path
) -> None:
    admin_client, alice_client, _bob = two_user_clients
    target = tmp_path / "auto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(target)], check=True)
    team = _mk_team(
        admin_client,
        name="auto-team",
        path_prefix="auto",
        git_remote_url=str(target),
        git_branch="main",
        git_push=True,
    )
    admin_client.post(f"/api/v1/teams/{team['id']}/members/alice")
    subprocess.run(["git", "init", "-q", "-b", "main", str(bundle_dir)], check=True)

    draft = alice_client.post(
        "/api/v1/drafts", json={"bundle": "test", "rel_path": "auto/pipeline.py"}
    ).json()
    deploy = alice_client.post(
        f"/api/v1/drafts/{draft['id']}/deploy", json={"expected_file_hash": None}
    ).json()
    assert deploy["git_pushed"] is True, deploy
    assert deploy["git_commit_sha"] is not None
    log = subprocess.run(
        ["git", "-C", str(target), "log", "main", "-1", "--format=%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "auto/pipeline.py" in log.stdout


def test_remote_commit_url_parsing(tmp_path: Path) -> None:
    from dagsmith.core.gitops import remote_commit_url
    from dagsmith.core.storage import BundleRef

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    bundle = BundleRef(name="r", root=root.resolve(), writable=True)

    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", "git@github.com:acme/dags.git"],
        check=True,
    )
    assert remote_commit_url(bundle, "abc123") == "https://github.com/acme/dags/commit/abc123"

    subprocess.run(
        ["git", "-C", str(root), "remote", "set-url", "origin",
         "https://gitlab.com/acme/dags.git"],
        check=True,
    )
    assert (
        remote_commit_url(bundle, "abc123") == "https://gitlab.com/acme/dags/-/commit/abc123"
    )
