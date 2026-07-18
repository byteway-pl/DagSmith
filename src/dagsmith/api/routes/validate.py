from __future__ import annotations

from fastapi import APIRouter, Depends

from dagsmith.api.schemas import ValidateRequest, ValidateResult
from dagsmith.api.security import require_edit
from dagsmith.core.validation import validate_source

# Deep validation executes user code (in a subprocess) — editor permission required.
router = APIRouter(tags=["validate"], dependencies=[Depends(require_edit)])


@router.post("/validate")
def validate(body: ValidateRequest) -> ValidateResult:
    return validate_source(body.source, deep=body.deep)
