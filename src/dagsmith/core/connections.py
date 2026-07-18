"""Read-only listing of Airflow connections for the conn_id pickers.

Sources:
- the ``connection`` table in the Airflow metadata DB — read with DagSmith's
  own engine via a plain SELECT (we never touch Airflow's ORM sessions),
- ``AIRFLOW_CONN_*`` environment variables.

Connections held only in a secrets backend are not enumerable — the UI keeps
free-text input for that reason. Failures degrade to an empty/partial list.
"""

from __future__ import annotations

import logging
import os

import sqlalchemy as sa

from dagsmith.core.db import get_engine

log = logging.getLogger(__name__)


def list_connections() -> list[dict[str, str | None]]:
    connections: dict[str, str | None] = {}

    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                sa.text("SELECT conn_id, conn_type FROM connection ORDER BY conn_id")
            )
            for conn_id, conn_type in rows:
                connections[conn_id] = conn_type
    except Exception as exc:
        log.info("Cannot read the connection table: %s", exc)

    for key, value in os.environ.items():
        if key.startswith("AIRFLOW_CONN_"):
            conn_id = key.removeprefix("AIRFLOW_CONN_").lower()
            # URI-style values start with "<type>://"
            conn_type = value.split("://", 1)[0] if "://" in value else None
            connections.setdefault(conn_id, conn_type)

    return [
        {"conn_id": conn_id, "conn_type": conn_type}
        for conn_id, conn_type in sorted(connections.items())
    ]
