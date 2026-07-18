"""Alembic environment for the DagSmith migration chain.

Uses its own version table (``dagsmith_alembic_version``) so it never collides
with Airflow's Alembic chain living in the same database.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from dagsmith.core import db
from dagsmith.core.migrate import VERSION_TABLE

config = context.config
target_metadata = db.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        version_table=VERSION_TABLE,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
