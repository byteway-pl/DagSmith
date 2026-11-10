from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import orm

from dagsmith.api.deps import db_session
from dagsmith.api.errors import BadRequestError
from dagsmith.api.schemas import ValidateRequest, ValidateResult
from dagsmith.api.security import ApiUser, is_admin, require_edit
from dagsmith.core import storage, teams
from dagsmith.core.validation import validate_source

router = APIRouter(tags=["validate"])


@router.post("/validate")
def validate(
    body: ValidateRequest,
    user: ApiUser = Depends(require_edit),
    session: orm.Session = Depends(db_session),
) -> ValidateResult:
    paths = None
    if (body.bundle is None) != (body.rel_path is None):
        raise BadRequestError("bundle and rel_path must be supplied together")
    if body.bundle is not None and body.rel_path is not None:
        bundle = storage.get_bundle(body.bundle)
        candidate = storage.safe_resolve(bundle, body.rel_path, must_exist=False)
        teams.ensure_file_access(session, body.bundle, body.rel_path, user.username, is_admin(user))
        paths = [candidate.parent, bundle.root]
    return validate_source(body.source, deep=body.deep, import_paths=paths)
