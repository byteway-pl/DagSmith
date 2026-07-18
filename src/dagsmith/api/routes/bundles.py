from __future__ import annotations

from fastapi import APIRouter, Depends

from dagsmith.api.schemas import BundleInfo
from dagsmith.api.security import require_read
from dagsmith.core import storage
from dagsmith.core.gitops import is_git_repo

router = APIRouter(tags=["bundles"], dependencies=[Depends(require_read)])


@router.get("/bundles")
def list_bundles() -> list[BundleInfo]:
    return [
        BundleInfo(name=b.name, path=str(b.root), writable=b.writable, git=is_git_repo(b))
        for b in storage.list_bundles()
    ]
