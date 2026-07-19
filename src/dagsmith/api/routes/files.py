"""Read-only access to live files. The only write path to disk is deploy."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import orm, select

from dagsmith.api.deps import db_session
from dagsmith.api.schemas import FileContent, FileInfo
from dagsmith.api.security import ApiUser, is_admin, require_read
from dagsmith.core import drafts as drafts_core
from dagsmith.core import storage
from dagsmith.core import teams as teams_core
from dagsmith.core.db import Draft
from dagsmith.core.model import DagMeta
from dagsmith.core.parser import parse_meta

router = APIRouter(tags=["files"])

# Cache parsed metadata keyed by (bundle, rel_path, size, mtime) so unchanged
# files aren't re-parsed with libcst on every listing.
_META_CACHE: dict[tuple[str, str, int, float], DagMeta | None] = {}
_META_CACHE_MAX = 2048


def _file_meta(
    bundle_ref: storage.BundleRef, bundle: str, rel_path: str, size: int, mtime: float
) -> DagMeta | None:
    key = (bundle, rel_path, size, mtime)
    if key in _META_CACHE:
        return _META_CACHE[key]
    try:
        source, _digest, _mtime = storage.read_file(bundle_ref, rel_path)
        meta = parse_meta(source)
    except Exception:
        meta = None
    if len(_META_CACHE) >= _META_CACHE_MAX:
        _META_CACHE.clear()
    _META_CACHE[key] = meta
    return meta


@router.get("/files")
def list_files(
    bundle: str,
    user: ApiUser = Depends(require_read),
    session: orm.Session = Depends(db_session),
) -> list[FileInfo]:
    bundle_ref = storage.get_bundle(bundle)
    active_drafts = list(
        session.scalars(
            select(Draft).where(Draft.bundle == bundle, Draft.status != "archived")
        )
    )
    drafts_by_path = {d.rel_path: d for d in active_drafts}
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

    def entry(
        rel_path: str, size: int, mtime, meta: DagMeta | None, deployed: bool
    ) -> FileInfo:
        team = owning_team(rel_path)
        draft = drafts_by_path.get(rel_path)
        return FileInfo(
            rel_path=rel_path,
            size=size,
            mtime=mtime,
            has_draft=draft is not None,
            deployed=deployed,
            dag_id=meta.dag_id if meta else None,
            description=meta.description if meta else None,
            tags=meta.tags if meta else [],
            owner=meta.owner if meta else None,
            created_by=draft.created_by if draft else None,
            team=team.name if team else None,
            editable=team is None or admin or team.id in my_team_ids,
        )

    results: list[FileInfo] = []
    on_disk: set[str] = set()
    for rel_path, size, mtime in storage.list_py_files(bundle_ref):
        on_disk.add(rel_path)
        meta = _file_meta(bundle_ref, bundle, rel_path, size, mtime.timestamp())
        results.append(entry(rel_path, size, mtime, meta, deployed=True))

    # Drafts with no file on disk yet (created, saved, never deployed) still
    # need to be reachable — surface them with deployed=False instead of
    # silently dropping them from the listing.
    for draft in active_drafts:
        if draft.rel_path in on_disk:
            continue
        try:
            source = drafts_core.get_head_version(session, draft).source
            meta = parse_meta(source)
        except Exception:
            meta = None
        results.append(
            entry(draft.rel_path, 0, draft.updated_at, meta, deployed=False)
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
