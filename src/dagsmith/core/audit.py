"""Append-only JSONL audit log of deploy operations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from dagsmith.core.storage import dagsmith_home


def log_event(action: str, user: str | None, **fields: Any) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "user": user,
        **fields,
    }
    path = dagsmith_home() / "audit.log"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_events(limit: int = 100) -> list[dict[str, Any]]:
    """Most recent audit entries, newest first."""
    path = dagsmith_home() / "audit.log"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return list(reversed(events[-limit:]))
