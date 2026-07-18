"""Pydantic schemas of the DagSmith REST API (v1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

VersionKind = Literal["auto", "manual", "deploy"]
DraftStatus = Literal["active", "deployed", "archived"]
ErrorKind = Literal["syntax", "import", "dag", "timeout"]


class BundleInfo(BaseModel):
    name: str
    path: str
    writable: bool
    git: bool = False


class FileInfo(BaseModel):
    rel_path: str
    size: int
    mtime: datetime
    has_draft: bool = False
    # Owning team (by path prefix) and whether the current user may edit it.
    team: str | None = None
    editable: bool = True


class FileContent(BaseModel):
    bundle: str
    rel_path: str
    content: str
    content_hash: str
    mtime: datetime


class DraftSummary(BaseModel):
    id: str
    bundle: str
    rel_path: str
    status: DraftStatus
    head_version_no: int
    base_file_hash: str | None
    created_by: str | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DraftDetail(DraftSummary):
    source: str
    layout: dict[str, Any] | None
    # Hash of the live file right now (None = file does not exist on disk).
    live_file_hash: str | None
    # True when the live file changed outside DagSmith since the draft was branched.
    live_conflict: bool


class VersionInfo(BaseModel):
    version_no: int
    kind: VersionKind
    message: str | None
    created_by: str | None
    created_at: datetime
    deployed_at: datetime | None

    model_config = {"from_attributes": True}


class VersionDetail(VersionInfo):
    source: str
    layout: dict[str, Any] | None


class DraftCreate(BaseModel):
    bundle: str
    rel_path: str = Field(pattern=r".+\.py$")


class VersionCreate(BaseModel):
    source: str
    layout: dict[str, Any] | None = None
    kind: Literal["auto", "manual"] = "manual"
    message: str | None = Field(default=None, max_length=500)
    expected_head_version_no: int


class ValidationIssue(BaseModel):
    line: int | None = None
    col: int | None = None
    message: str
    kind: ErrorKind


class ValidateRequest(BaseModel):
    source: str
    # Deep validation imports the file in a subprocess (executes top-level code).
    deep: bool = True


class ValidateResult(BaseModel):
    ok: bool
    errors: list[ValidationIssue]
    dag_count: int | None = None


class DeployRequest(BaseModel):
    # Version to deploy; defaults to the draft head.
    version_no: int | None = None
    # Hash of the live file content the client last saw; None = file should not exist yet.
    expected_file_hash: str | None = None


class DeployResult(BaseModel):
    deployed_version_no: int
    file_hash: str
    backup_path: str | None
    git_commit_sha: str | None = None
    git_pushed: bool = False
    git_error: str | None = None


class AuditEntry(BaseModel):
    ts: str
    action: str
    user: str | None = None
    bundle: str | None = None
    rel_path: str | None = None
    draft_id: str | None = None
    version_no: int | None = None
    hash_before: str | None = None
    hash_after: str | None = None
    backup_path: str | None = None
    git_commit_sha: str | None = None
    git_pushed: bool = False
    git_error: str | None = None

    model_config = {"extra": "ignore"}


class ConfigInfo(BaseModel):
    deploy_enabled: bool
    autosave_interval: int
    can_edit: bool
    can_deploy: bool
    is_admin: bool = False
    username: str | None


class TeamInfo(BaseModel):
    id: str
    name: str
    description: str | None
    bundle: str
    path_prefix: str
    git_remote_url: str | None
    git_branch: str
    git_push: bool
    members: list[str]


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    bundle: str
    path_prefix: str = ""
    git_remote_url: str | None = None
    git_branch: str = "main"
    git_push: bool = False


class FileTeamAssign(BaseModel):
    bundle: str
    rel_path: str
    # None clears the override (back to directory-based ownership).
    team_id: str | None = None


class FileTeamResult(BaseModel):
    bundle: str
    rel_path: str
    team: str | None


class GitPushResult(BaseModel):
    commit_sha: str | None
    pushed: bool
    error: str | None
    web_url: str | None = None
