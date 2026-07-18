"""Unauthenticated liveness endpoint (the only one exempt from auth)."""

from __future__ import annotations

from fastapi import APIRouter

from dagsmith import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
