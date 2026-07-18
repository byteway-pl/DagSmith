"""Graph model of a DAG — the canvas projection exchanged with the frontend.

The model is intentionally minimal in M2 (visual→code only). It grows in M3
(parser output: opaque regions) and M4 (task groups).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Airflow allows dots and dashes in dag_id/task_id; Python identifiers are a subset.
AIRFLOW_ID_RE = re.compile(r"^[A-Za-z_][\w.\-]*$")


class Position(BaseModel):
    x: float
    y: float


class TaskNode(BaseModel):
    # Node id doubles as the Airflow task_id.
    id: str
    block_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    position: Position | None = None
    # Opaque: recognized as a task but not editable visually (unknown operator,
    # dynamic construct). Kept verbatim by the transforming codegen.
    opaque: bool = False
    # TaskGroup membership (dotted for nesting, e.g. "outer.inner"); None = top level.
    group_id: str | None = None

    @field_validator("id")
    @classmethod
    def _valid_task_id(cls, value: str) -> str:
        if not AIRFLOW_ID_RE.match(value):
            raise ValueError(f"invalid task id: {value!r}")
        return value


class Edge(BaseModel):
    source: str
    target: str
    # Airflow edge label: `a >> Label("x") >> b`.
    label: str | None = None


class TaskGroupNode(BaseModel):
    """A TaskGroup parsed from code. Read-only container in M4 (code-only edits)."""

    id: str
    label: str | None = None
    parent_id: str | None = None


class DagMeta(BaseModel):
    dag_id: str
    schedule: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    # ISO date "YYYY-MM-DD"; rendered as pendulum.datetime(...) in code.
    start_date: str | None = None
    catchup: bool | None = None
    max_active_runs: int | None = None
    # default_args (unknown keys in an existing dict are preserved by codegen)
    owner: str | None = None
    email: str | None = None
    retries: int | None = None
    retry_delay_s: int | None = None

    @field_validator("dag_id")
    @classmethod
    def _valid_dag_id(cls, value: str) -> str:
        if not AIRFLOW_ID_RE.match(value):
            raise ValueError(f"invalid dag_id: {value!r}")
        return value


class GraphModel(BaseModel):
    dag: DagMeta
    nodes: list[TaskNode] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    groups: list[TaskGroupNode] = Field(default_factory=list)


class GraphValidationError(ValueError):
    """Raised by codegen when the graph is structurally invalid."""
