from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from dagsmith.api.security import require_read
from dagsmith.core.catalog import BlockDef, catalog_fingerprint, list_blocks
from dagsmith.core.connections import list_connections

router = APIRouter(tags=["catalog"], dependencies=[Depends(require_read)])


class ConnectionInfo(BaseModel):
    conn_id: str
    conn_type: str | None


@router.get("/connections")
def connections() -> list[ConnectionInfo]:
    """Known Airflow connections (metadata DB + AIRFLOW_CONN_* env) for pickers."""
    return [ConnectionInfo(**item) for item in list_connections()]


@router.get("/operators", response_model=list[BlockDef])
def operators(request: Request, response: Response):
    # Fingerprint covers the full schema (params included), so any change to
    # the catalog — not just block ids — invalidates browser caches.
    etag = f'W/"{catalog_fingerprint()}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    response.headers["ETag"] = etag
    return list_blocks()
