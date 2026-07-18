"""FastAPI application mounted by Airflow under ``/dagsmith`` (see plugin.py)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from dagsmith import __version__
from dagsmith.api.errors import register_error_handlers
from dagsmith.api.routes import (
    audit,
    bundles,
    catalog,
    config,
    drafts,
    files,
    graph,
    health,
    teams,
    validate,
)
from dagsmith.config import get_bool

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if get_bool("auto_migrate"):
        try:
            from dagsmith.core.migrate import run_migrations

            run_migrations("upgrade", "head")
            log.info("DagSmith DB migrations applied")
        except Exception:
            # Never take the api-server down over a migration problem; endpoints
            # depending on the tables will fail loudly on their own.
            log.exception("DagSmith automatic DB migration failed")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="DagSmith",
        version=__version__,
        lifespan=_lifespan,
    )
    register_error_handlers(app)
    for router in (
        health.router,
        config.router,
        bundles.router,
        files.router,
        drafts.router,
        validate.router,
        graph.router,
        catalog.router,
        audit.router,
        teams.router,
    ):
        app.include_router(router, prefix="/api/v1")

    if STATIC_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=STATIC_DIR), name="ui")

        @app.middleware("http")
        async def _ui_no_cache(request, call_next):  # type: ignore[no-untyped-def]
            # The Airflow UI loads the bundle via dynamic import(); without an
            # explicit Cache-Control browsers apply heuristic caching and keep
            # serving stale bundles. no-cache = always revalidate (a cheap 304
            # via ETag when unchanged, fresh content the moment it changes).
            response = await call_next(request)
            if "/ui/" in request.url.path:
                response.headers["Cache-Control"] = "no-cache"
            return response

    return app
