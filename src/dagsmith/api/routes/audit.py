from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dagsmith.api.schemas import AuditEntry
from dagsmith.api.security import require_edit
from dagsmith.core import audit

router = APIRouter(tags=["audit"], dependencies=[Depends(require_edit)])


@router.get("/audit")
def audit_log(limit: int = Query(default=100, ge=1, le=1000)) -> list[AuditEntry]:
    return [AuditEntry.model_validate(event) for event in audit.read_events(limit)]
