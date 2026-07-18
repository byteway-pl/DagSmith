"""Draft CRUD, version history and the deploy endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import orm

from dagsmith.api.deps import db_session
from dagsmith.api.errors import BadRequestError
from dagsmith.api.schemas import (
    DeployRequest,
    DeployResult,
    DraftCreate,
    DraftDetail,
    DraftSummary,
    GitPushResult,
    VersionCreate,
    VersionDetail,
    VersionInfo,
)
from dagsmith.api.security import (
    ApiUser,
    is_admin,
    require_deploy,
    require_edit,
    require_read,
)
from dagsmith.core import audit, gitops, storage
from dagsmith.core import drafts as drafts_core
from dagsmith.core import teams as teams_core
from dagsmith.core.db import Draft, Team

router = APIRouter(tags=["drafts"])


def _ensure_access(
    session: orm.Session, user: ApiUser, bundle: str, rel_path: str
) -> Team | None:
    """Team-ownership gate on top of the global permission checks."""
    return teams_core.ensure_file_access(
        session, bundle, rel_path, user.username, is_admin(user)
    )


def _detail(session: orm.Session, draft: Draft) -> DraftDetail:
    head = drafts_core.get_head_version(session, draft)
    bundle_ref = storage.get_bundle(draft.bundle)
    live_hash = storage.file_hash_or_none(bundle_ref, draft.rel_path)
    return DraftDetail(
        **DraftSummary.model_validate(draft).model_dump(),
        source=head.source,
        layout=head.layout,
        live_file_hash=live_hash,
        live_conflict=live_hash != draft.base_file_hash,
    )


@router.get("/drafts")
def list_drafts(
    bundle: str | None = None,
    status: str | None = None,
    _user: ApiUser = Depends(require_read),
    session: orm.Session = Depends(db_session),
) -> list[DraftSummary]:
    return [
        DraftSummary.model_validate(d)
        for d in drafts_core.list_drafts(session, bundle=bundle, status=status)
    ]


@router.post("/drafts", status_code=201)
def create_or_open_draft(
    body: DraftCreate,
    user: ApiUser = Depends(require_edit),
    session: orm.Session = Depends(db_session),
) -> DraftDetail:
    bundle_ref = storage.get_bundle(body.bundle)
    # Path safety even though nothing is written yet: fail fast on bad input.
    storage.safe_resolve(bundle_ref, body.rel_path, must_exist=False)
    team = _ensure_access(session, user, body.bundle, body.rel_path)
    draft = drafts_core.create_or_open_draft(
        session,
        bundle_ref,
        body.rel_path,
        user.username,
        team_name=team.name if team else None,
    )
    session.flush()
    return _detail(session, draft)


@router.get("/drafts/{draft_id}")
def get_draft(
    draft_id: str,
    _user: ApiUser = Depends(require_read),
    session: orm.Session = Depends(db_session),
) -> DraftDetail:
    return _detail(session, drafts_core.get_draft(session, draft_id))


@router.delete("/drafts/{draft_id}", status_code=204)
def archive_draft(
    draft_id: str,
    user: ApiUser = Depends(require_edit),
    session: orm.Session = Depends(db_session),
) -> None:
    draft = drafts_core.get_draft(session, draft_id)
    _ensure_access(session, user, draft.bundle, draft.rel_path)
    drafts_core.archive_draft(session, draft, user.username)


@router.put("/drafts/{draft_id}/versions")
def save_version(
    draft_id: str,
    body: VersionCreate,
    user: ApiUser = Depends(require_edit),
    session: orm.Session = Depends(db_session),
) -> VersionInfo:
    draft = drafts_core.get_draft(session, draft_id)
    _ensure_access(session, user, draft.bundle, draft.rel_path)
    version = drafts_core.save_version(
        session,
        draft,
        source=body.source,
        layout=body.layout,
        kind=body.kind,
        message=body.message,
        expected_head_version_no=body.expected_head_version_no,
        user=user.username,
    )
    session.flush()
    return VersionInfo.model_validate(version)


@router.get("/drafts/{draft_id}/versions")
def list_versions(
    draft_id: str,
    _user: ApiUser = Depends(require_read),
    session: orm.Session = Depends(db_session),
) -> list[VersionInfo]:
    draft = drafts_core.get_draft(session, draft_id)
    return [VersionInfo.model_validate(v) for v in drafts_core.list_versions(session, draft)]


@router.get("/drafts/{draft_id}/versions/{version_no}")
def get_version(
    draft_id: str,
    version_no: int,
    _user: ApiUser = Depends(require_read),
    session: orm.Session = Depends(db_session),
) -> VersionDetail:
    draft = drafts_core.get_draft(session, draft_id)
    return VersionDetail.model_validate(drafts_core.get_version(session, draft, version_no))


@router.post("/drafts/{draft_id}/reload")
def reload_from_file(
    draft_id: str,
    user: ApiUser = Depends(require_edit),
    session: orm.Session = Depends(db_session),
) -> DraftDetail:
    """Load the current on-disk (deployed) file into the draft, discarding edits."""
    draft = drafts_core.get_draft(session, draft_id)
    _ensure_access(session, user, draft.bundle, draft.rel_path)
    bundle_ref = storage.get_bundle(draft.bundle)
    drafts_core.reload_from_file(session, draft, bundle_ref, user.username)
    session.flush()
    return _detail(session, draft)


@router.post("/drafts/{draft_id}/restore/{version_no}")
def restore_version(
    draft_id: str,
    version_no: int,
    user: ApiUser = Depends(require_edit),
    session: orm.Session = Depends(db_session),
) -> VersionInfo:
    draft = drafts_core.get_draft(session, draft_id)
    _ensure_access(session, user, draft.bundle, draft.rel_path)
    version = drafts_core.restore_version(session, draft, version_no, user.username)
    session.flush()
    return VersionInfo.model_validate(version)


@router.post("/drafts/{draft_id}/git-push")
def git_push(
    draft_id: str,
    user: ApiUser = Depends(require_deploy),
    session: orm.Session = Depends(db_session),
) -> GitPushResult:
    """Commit the live file to the bundle's git repo and push to its remote."""
    draft = drafts_core.get_draft(session, draft_id)
    team = _ensure_access(session, user, draft.bundle, draft.rel_path)
    bundle_ref = storage.get_bundle(draft.bundle)
    if not gitops.is_git_repo(bundle_ref):
        raise BadRequestError(f"Bundle {draft.bundle!r} is not a git repository")
    head = drafts_core.get_head_version(session, draft)
    result = gitops.commit_deploy(
        bundle_ref,
        draft.rel_path,
        user.username,
        message=f"dagsmith: update {draft.rel_path} (draft v{head.version_no})",
        push=False,
    )
    # Push target: the team's configured repository/branch override, otherwise
    # the bundle checkout's own upstream (its origin).
    remote_url = team.git_remote_url if team else None
    branch = team.git_branch if team and team.git_remote_url else None
    pushed = False
    error = result.error
    if error is None:
        pushed, push_error = gitops.push_head(bundle_ref, remote_url, branch)
        error = push_error
    web_url = (
        gitops.remote_commit_url(bundle_ref, result.commit_sha, remote_url=remote_url)
        if result.commit_sha
        else None
    )
    audit.log_event(
        "git_push",
        user.username,
        bundle=draft.bundle,
        rel_path=draft.rel_path,
        draft_id=draft.id,
        git_commit_sha=result.commit_sha,
        git_pushed=pushed,
        git_error=error,
        git_remote=remote_url,
        git_branch=branch,
    )
    return GitPushResult(
        commit_sha=result.commit_sha,
        pushed=pushed,
        error=error,
        web_url=web_url,
    )


@router.post("/drafts/{draft_id}/deploy")
def deploy(
    draft_id: str,
    body: DeployRequest,
    user: ApiUser = Depends(require_deploy),
    session: orm.Session = Depends(db_session),
) -> DeployResult:
    draft = drafts_core.get_draft(session, draft_id)
    team = _ensure_access(session, user, draft.bundle, draft.rel_path)
    bundle_ref = storage.get_bundle(draft.bundle)
    # Deploy always targets the bundle (incl. its checkout's git when the
    # global git_commit is on); the team's repo is an additional push target.
    version, new_hash, backup_path, git_result = drafts_core.deploy(
        session,
        draft,
        bundle_ref,
        version_no=body.version_no,
        expected_file_hash=body.expected_file_hash,
        user=user.username,
    )
    git_sha = git_result.commit_sha if git_result else None
    git_pushed = git_result.pushed if git_result else False
    git_error = git_result.error if git_result else None
    # Team auto-push: commit and push to the team's repository/branch override,
    # or to the bundle checkout's own upstream when no override is set.
    if team is not None and team.git_push and gitops.is_git_repo(bundle_ref):
        commit_result = gitops.commit_deploy(
            bundle_ref,
            draft.rel_path,
            user.username,
            message=f"dagsmith: deploy {draft.rel_path} (draft v{version.version_no})",
            push=False,
        )
        git_sha = commit_result.commit_sha or git_sha
        if commit_result.error is None:
            git_pushed, git_error = gitops.push_head(
                bundle_ref, team.git_remote_url, team.git_branch
            )
        else:
            git_error = commit_result.error
    return DeployResult(
        deployed_version_no=version.version_no,
        file_hash=new_hash,
        backup_path=backup_path,
        git_commit_sha=git_sha,
        git_pushed=git_pushed,
        git_error=git_error,
    )
