"""Draft lifecycle: create, save versions, restore, deploy.

Pure business logic operating on a SQLAlchemy session — no FastAPI here.
Concurrency rules (ARCHITECTURE.md §4.3):
- saving a version requires ``expected_head_version_no`` (409 on mismatch),
- deploying requires ``expected_file_hash`` of the live file (409 on mismatch).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import orm, select

from dagsmith.api.errors import ConflictError, NotFoundError, ValidationFailedError
from dagsmith.config import get_bool, get_int
from dagsmith.core import audit, storage
from dagsmith.core.db import Draft, DraftVersion
from dagsmith.core.gitops import GitResult, commit_deploy, is_git_repo

NEW_DAG_TEMPLATE = '''# dagsmith: v1
"""DAG created with DagSmith."""

from __future__ import annotations

from airflow.sdk import dag


@dag(schedule=None, tags={tags!r})
def {dag_id}():
    pass


{dag_id}()
'''


def _dag_id_from_path(rel_path: str) -> str:
    stem = rel_path.rsplit("/", 1)[-1].removesuffix(".py")
    dag_id = re.sub(r"\W", "_", stem)
    if not dag_id or dag_id[0].isdigit():
        dag_id = f"dag_{dag_id}"
    return dag_id


def list_drafts(
    session: orm.Session, bundle: str | None = None, status: str | None = None
) -> list[Draft]:
    stmt = select(Draft).order_by(Draft.updated_at.desc())
    if bundle:
        stmt = stmt.where(Draft.bundle == bundle)
    if status:
        stmt = stmt.where(Draft.status == status)
    return list(session.scalars(stmt))


def get_draft(session: orm.Session, draft_id: str) -> Draft:
    draft = session.get(Draft, draft_id)
    if draft is None or draft.status == "archived":
        raise NotFoundError(f"Draft not found: {draft_id}")
    return draft


def get_head_version(session: orm.Session, draft: Draft) -> DraftVersion:
    version = session.scalars(
        select(DraftVersion)
        .where(DraftVersion.draft_id == draft.id)
        .where(DraftVersion.version_no == draft.head_version_no)
    ).first()
    if version is None:
        raise NotFoundError(f"Head version missing for draft {draft.id}")
    return version


def get_version(session: orm.Session, draft: Draft, version_no: int) -> DraftVersion:
    version = session.scalars(
        select(DraftVersion)
        .where(DraftVersion.draft_id == draft.id)
        .where(DraftVersion.version_no == version_no)
    ).first()
    if version is None:
        raise NotFoundError(f"Version {version_no} not found for draft {draft.id}")
    return version


def list_versions(session: orm.Session, draft: Draft) -> list[DraftVersion]:
    return list(
        session.scalars(
            select(DraftVersion)
            .where(DraftVersion.draft_id == draft.id)
            .order_by(DraftVersion.version_no.desc())
        )
    )


def create_or_open_draft(
    session: orm.Session,
    bundle: storage.BundleRef,
    rel_path: str,
    user: str | None,
    team_name: str | None = None,
) -> Draft:
    """Open the shared draft for a file, creating it (branched from live) if absent."""
    existing = session.scalars(
        select(Draft).where(Draft.bundle == bundle.name, Draft.rel_path == rel_path)
    ).first()
    if existing is not None:
        if existing.status == "archived":
            existing.status = "active"
            existing.updated_by = user
        return existing

    live_hash: str | None = None
    path = storage.safe_resolve(bundle, rel_path, must_exist=False)
    if path.is_file():
        source, live_hash, _ = storage.read_file(bundle, rel_path)
    else:
        # New DAGs created by a team member are tagged with the team, so the
        # native Airflow DAG list can be filtered per team.
        tags = [f"team:{team_name}"] if team_name else ["dagsmith"]
        source = NEW_DAG_TEMPLATE.format(dag_id=_dag_id_from_path(rel_path), tags=tags)

    draft = Draft(
        bundle=bundle.name,
        rel_path=rel_path,
        base_file_hash=live_hash,
        head_version_no=1,
        status="active",
        created_by=user,
        updated_by=user,
    )
    session.add(draft)
    session.flush()
    session.add(
        DraftVersion(
            draft_id=draft.id,
            version_no=1,
            source=source,
            kind="manual",
            message="initial (branched from live file)" if live_hash else "initial (new file)",
            created_by=user,
        )
    )
    return draft


def save_version(
    session: orm.Session,
    draft: Draft,
    *,
    source: str,
    layout: dict[str, Any] | None,
    kind: str,
    message: str | None,
    expected_head_version_no: int,
    user: str | None,
) -> DraftVersion:
    if draft.head_version_no != expected_head_version_no:
        raise ConflictError(
            "Draft was modified by someone else",
            detail={"head_version_no": draft.head_version_no},
        )
    version = DraftVersion(
        draft_id=draft.id,
        version_no=draft.head_version_no + 1,
        source=source,
        layout=layout,
        kind=kind,
        message=message,
        created_by=user,
    )
    session.add(version)
    draft.head_version_no = version.version_no
    draft.status = "active"
    draft.updated_by = user
    if kind == "auto":
        _compact_autosaves(session, draft)
    return version


def _compact_autosaves(session: orm.Session, draft: Draft) -> None:
    keep = get_int("auto_versions_keep")
    autos = list(
        session.scalars(
            select(DraftVersion)
            .where(DraftVersion.draft_id == draft.id, DraftVersion.kind == "auto")
            .order_by(DraftVersion.version_no.desc())
        )
    )
    for stale in autos[keep:]:
        session.delete(stale)


def reload_from_file(
    session: orm.Session, draft: Draft, bundle: storage.BundleRef, user: str | None
) -> DraftVersion:
    """Load the live (deployed) file content into the draft as a new head version.

    Discards nothing from history — it appends. Realigns ``base_file_hash`` so the
    draft is back in sync with what is on disk.
    """
    path = storage.safe_resolve(bundle, draft.rel_path, must_exist=False)
    if not path.is_file():
        raise NotFoundError(f"No deployed file to load: {draft.rel_path}")
    source, live_hash, _ = storage.read_file(bundle, draft.rel_path)
    version = save_version(
        session,
        draft,
        source=source,
        layout=None,
        kind="manual",
        message="loaded from bundle (deployed file)",
        expected_head_version_no=draft.head_version_no,
        user=user,
    )
    draft.base_file_hash = live_hash
    return version


def restore_version(
    session: orm.Session, draft: Draft, version_no: int, user: str | None
) -> DraftVersion:
    old = get_version(session, draft, version_no)
    return save_version(
        session,
        draft,
        source=old.source,
        layout=old.layout,
        kind="manual",
        message=f"restore of v{version_no}",
        expected_head_version_no=draft.head_version_no,
        user=user,
    )


def archive_draft(session: orm.Session, draft: Draft, user: str | None) -> None:
    draft.status = "archived"
    draft.updated_by = user


def deploy(
    session: orm.Session,
    draft: Draft,
    bundle: storage.BundleRef,
    *,
    version_no: int | None,
    expected_file_hash: str | None,
    user: str | None,
    allow_global_git: bool = True,
) -> tuple[DraftVersion, str, str | None, GitResult | None]:
    """Validate and write the draft version to the live file.

    ``allow_global_git=False`` skips the global ``git_commit`` auto-commit —
    used for team-owned files, where git is driven by the team's repo config.
    Returns (deployed_version, new_file_hash, backup_path, git_result).
    """
    version = (
        get_head_version(session, draft)
        if version_no is None
        else get_version(session, draft, version_no)
    )

    from dagsmith.core.validation import validate_source

    result = validate_source(version.source, deep=True)
    if not result.ok:
        raise ValidationFailedError(
            "Validation failed",
            detail={"errors": [issue.model_dump() for issue in result.errors]},
        )

    live_hash = storage.file_hash_or_none(bundle, draft.rel_path)
    if live_hash != expected_file_hash:
        current_content: str | None = None
        if live_hash is not None:
            current_content, _, _ = storage.read_file(bundle, draft.rel_path)
        raise ConflictError(
            "Live file changed outside DagSmith",
            detail={"live_file_hash": live_hash, "live_content": current_content},
        )

    backup_path = storage.backup_file(bundle, draft.rel_path)
    new_hash = storage.write_file_atomic(bundle, draft.rel_path, version.source)

    git_result: GitResult | None = None
    if allow_global_git and get_bool("git_commit") and is_git_repo(bundle):
        git_result = commit_deploy(
            bundle,
            draft.rel_path,
            user,
            message=f"dagsmith: deploy {draft.rel_path} (draft v{version.version_no})",
            push=get_bool("git_push"),
        )

    version.deployed_at = datetime.now(timezone.utc)
    if version.kind != "deploy":
        version.message = version.message or f"deployed as v{version.version_no}"
    draft.base_file_hash = new_hash
    draft.status = "deployed"
    draft.updated_by = user

    audit.log_event(
        "deploy",
        user,
        bundle=bundle.name,
        rel_path=draft.rel_path,
        draft_id=draft.id,
        version_no=version.version_no,
        hash_before=live_hash,
        hash_after=new_hash,
        backup_path=backup_path,
        git_commit_sha=git_result.commit_sha if git_result else None,
        git_pushed=git_result.pushed if git_result else False,
        git_error=git_result.error if git_result else None,
    )
    return version, new_hash, backup_path, git_result
