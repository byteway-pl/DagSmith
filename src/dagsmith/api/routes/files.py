"""Read-only access to live files. The only write path to disk is deploy."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import orm, select

from dagsmith.api.deps import db_session
from dagsmith.api.schemas import FileContent, FileInfo
from dagsmith.api.security import ApiUser, is_admin, require_read
from dagsmith.core import storage
from dagsmith.core import teams as teams_core
from dagsmith.core.db import Draft

router = APIRouter(tags=["files"])


@router.get("/files")
def list_files(
    bundle: str,
    user: ApiUser = Depends(require_read),
    session: orm.Session = Depends(db_session),
) -> list[FileInfo]:
    bundle_ref = storage.get_bundle(bundle)
    drafted = set(
        session.scalars(
            select(Draft.rel_path).where(
                Draft.bundle == bundle, Draft.status != "archived"
            )
        )
    )
    bundle_teams = [t for t in teams_core.list_teams(session) if t.bundle == bundle]
    my_team_ids = {t.id for t in teams_core.user_teams(session, user.username)}
    overrides = teams_core.file_team_overrides(session, bundle)
    admin = is_admin(user)

    def owning_team(rel_path: str):
        # Admin per-file override wins over directory-based ownership.
        if rel_path in overrides:
            return overrides[rel_path]
        best = None
        for team in bundle_teams:
            prefix = team.path_prefix
            matches = prefix == "" or rel_path == prefix or rel_path.startswith(prefix + "/")
            if matches and (best is None or len(prefix) > len(best.path_prefix)):
                best = team
        return best

    results: list[FileInfo] = []
    for rel_path, size, mtime in storage.list_py_files(bundle_ref):
        team = owning_team(rel_path)
        results.append(
            FileInfo(
                rel_path=rel_path,
                size=size,
                mtime=mtime,
                has_draft=rel_path in drafted,
                team=team.name if team else None,
                editable=team is None or admin or team.id in my_team_ids,
            )
        )
    return results


@router.get("/files/{rel_path:path}", dependencies=[Depends(require_read)])
def read_file(bundle: str, rel_path: str) -> FileContent:
    bundle_ref = storage.get_bundle(bundle)
    content, digest, mtime = storage.read_file(bundle_ref, rel_path)
    return FileContent(
        bundle=bundle,
        rel_path=rel_path,
        content=content,
        content_hash=digest,
        mtime=mtime,
    )
