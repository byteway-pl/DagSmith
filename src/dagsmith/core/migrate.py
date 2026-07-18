"""Programmatic Alembic runner for the DagSmith migration chain."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

VERSION_TABLE = "dagsmith_alembic_version"
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _alembic_config(url: str | None = None) -> Config:
    if url is None:
        from dagsmith.config import sql_alchemy_url

        url = sql_alchemy_url()
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def run_migrations(action: str = "upgrade", revision: str = "head", url: str | None = None) -> None:
    """Run an Alembic command: ``upgrade``, ``downgrade`` or ``current``."""
    cfg = _alembic_config(url)
    if action == "upgrade":
        command.upgrade(cfg, revision)
    elif action == "downgrade":
        command.downgrade(cfg, revision)
    elif action == "current":
        command.current(cfg, verbose=True)
    else:
        raise ValueError(f"Unsupported migration action: {action}")
