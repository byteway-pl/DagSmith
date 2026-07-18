"""Graph -> Python source generation.

Two modes (ARCHITECTURE.md §4.5):
- from scratch (``base_source=None``): full ``# dagsmith: v1`` file,
- transform (``base_source`` given): minimal, formatting-preserving edits via
  libcst (see ``transform.py``). Invariant: an unchanged graph returns
  ``base_source`` byte-for-byte.
"""

from __future__ import annotations

import ast as pyast
import re
from collections import defaultdict

from dagsmith.core.catalog import BlockDef, get_block
from dagsmith.core.model import (
    IDENTIFIER_RE,
    DagMeta,
    GraphModel,
    GraphValidationError,
    TaskGroupNode,
    TaskNode,
)

INDENT = "    "


def sanitize_identifier(value: str) -> str:
    ident = re.sub(r"\W", "_", value)
    if not ident or ident[0].isdigit():
        ident = f"_{ident}"
    return ident


def var_name(node_id: str) -> str:
    return f"t_{sanitize_identifier(node_id)}"


def group_var_name(group_id: str) -> str:
    """Variable name for a TaskGroup used as a dependency endpoint."""
    return f"g_{sanitize_identifier(group_id.replace('.', '_'))}"


def edge_group_endpoints(graph: GraphModel) -> set[str]:
    """Group ids that appear as an edge source or target."""
    group_ids = {g.id for g in graph.groups}
    used: set[str] = set()
    for edge in graph.edges:
        if edge.source in group_ids:
            used.add(edge.source)
        if edge.target in group_ids:
            used.add(edge.target)
    return used


def dep_line(source_var: str, target_var: str, label: str | None) -> str:
    if label:
        return f"{source_var} >> Label({label!r}) >> {target_var}"
    return f"{source_var} >> {target_var}"


def start_date_code(iso_date: str) -> str:
    year, month, day = (int(part) for part in iso_date.split("-"))
    return f"pendulum.datetime({year}, {month}, {day})"


def default_args_code(
    meta: DagMeta, extras: list[tuple[str, str]] | None = None
) -> str | None:
    """Dict literal for default_args; ``extras`` are preserved raw entries."""
    parts: list[str] = []
    if meta.owner:
        parts.append(f"'owner': {meta.owner!r}")
    if meta.email:
        parts.append(f"'email': {meta.email!r}")
    if meta.retries is not None:
        parts.append(f"'retries': {meta.retries}")
    if meta.retry_delay_s is not None:
        parts.append(f"'retry_delay': timedelta(seconds={meta.retry_delay_s})")
    parts.extend(f"{key}: {value}" for key, value in extras or [])
    if not parts:
        return None
    return "{" + ", ".join(parts) + "}"


def validate_graph(graph: GraphModel, allow_opaque: bool = False) -> None:
    seen: set[str] = set()
    for node in graph.nodes:
        if node.id in seen:
            raise GraphValidationError(f"Duplicate task id: {node.id}")
        seen.add(node.id)
        if node.opaque or node.block_id == "opaque":
            if not allow_opaque:
                raise GraphValidationError(
                    f"Task {node.id!r} is opaque (code-only) — cannot generate from scratch"
                )
            continue
        try:
            get_block(node.block_id)
        except KeyError as exc:
            raise GraphValidationError(str(exc)) from exc
        if node.block_id == "python" and not IDENTIFIER_RE.match(node.id):
            raise GraphValidationError(
                f"Python task id must be a valid identifier, got: {node.id!r}"
            )
    # Edge endpoints may be tasks or TaskGroups.
    endpoints = seen | {group.id for group in graph.groups}
    for edge in graph.edges:
        if edge.source not in endpoints or edge.target not in endpoints:
            raise GraphValidationError(
                f"Edge references unknown task/group: {edge.source} -> {edge.target}"
            )
        if edge.source == edge.target:
            raise GraphValidationError(f"Self-loop on: {edge.source}")


def topo_order(graph: GraphModel) -> list[TaskNode]:
    """Kahn's algorithm over task-to-task edges; stable insertion order.

    Group-level edges don't constrain task *definition* order (dependency lines
    are emitted after all definitions), so they're ignored here.
    """
    indegree = {node.id: 0 for node in graph.nodes}
    task_edges = [e for e in graph.edges if e.source in indegree and e.target in indegree]
    for edge in task_edges:
        indegree[edge.target] += 1
    order: list[TaskNode] = []
    ready = [node for node in graph.nodes if indegree[node.id] == 0]
    while ready:
        node = ready.pop(0)
        order.append(node)
        for edge in task_edges:
            if edge.source == node.id:
                indegree[edge.target] -= 1
                if indegree[edge.target] == 0:
                    ready.append(next(n for n in graph.nodes if n.id == edge.target))
    if len(order) != len(graph.nodes):
        cyclic = sorted(set(indegree) - {n.id for n in order})
        raise GraphValidationError(f"Dependency cycle involving: {', '.join(cyclic)}")
    return order


def param_literal(value: object, param_type: str) -> str:
    if param_type == "int":
        return str(int(value))  # type: ignore[call-overload]
    if param_type == "bool":
        return "True" if value else "False"
    if param_type in ("python", "dict"):
        # Raw Python expression (e.g. a callable reference or a dict literal);
        # validated, not quoted.
        code = str(value).strip()
        try:
            pyast.parse(code, mode="eval")
        except SyntaxError as exc:
            raise GraphValidationError(
                f"Not a valid Python expression: {code!r}"
            ) from exc
        return code
    return repr(str(value))


def kwargs_for(node: TaskNode, block: BlockDef, skip: tuple[str, ...] = ()) -> list[str]:
    kwargs: list[str] = []
    for param in block.params:
        if param.name in skip:
            continue
        value = node.params.get(param.name, param.default if param.required else None)
        if param.required and (value is None or value == ""):
            raise GraphValidationError(
                f"Task {node.id!r}: required parameter {param.name!r} is empty"
            )
        if value is None or value == "":
            continue
        kwargs.append(f"{param.name}={param_literal(value, param.type)}")
    return kwargs


def emit_operator_lines(node: TaskNode) -> list[str]:
    """Unindented statement lines defining an operator task."""
    block = get_block(node.block_id)
    if not block.class_name:
        raise GraphValidationError(f"Block {node.block_id!r} has no operator class")
    kwargs = ", ".join([f'task_id="{node.id}"', *kwargs_for(node, block)])
    return [f"{var_name(node.id)} = {block.class_name}({kwargs})"]


def emit_python_lines(node: TaskNode) -> list[str]:
    """Unindented statement lines defining a @task function and its call."""
    block = get_block(node.block_id)
    body = str(node.params.get("body") or "pass")
    kwargs = kwargs_for(node, block, skip=("body",))
    decorator = f"@task({', '.join(kwargs)})" if kwargs else "@task"
    lines = [decorator, f"def {node.id}():"]
    for body_line in body.splitlines() or ["pass"]:
        lines.append(f"{INDENT}{body_line}" if body_line.strip() else "")
    lines.append(f"{var_name(node.id)} = {node.id}()")
    return lines


def emit_node_lines(node: TaskNode) -> list[str]:
    if node.block_id == "python":
        return emit_python_lines(node)
    return emit_operator_lines(node)


def _emit_dag_body(
    graph: GraphModel, order: list[TaskNode], group_vars: dict[str, str]
) -> list[str]:
    """DAG body lines (indented for the function/with block), incl. TaskGroups."""
    children_of: dict[str | None, list[TaskGroupNode]] = defaultdict(list)
    for group in graph.groups:
        children_of[group.parent_id].append(group)
    members_of: dict[str | None, list[TaskNode]] = defaultdict(list)
    for node in order:
        members_of[node.group_id].append(node)

    def emit_group(group: TaskGroupNode, depth: int) -> list[str]:
        pad = INDENT * (depth + 1)
        as_clause = f" as {group_vars[group.id]}" if group.id in group_vars else ""
        block = [f"{pad}with TaskGroup({(group.label or group.id)!r}){as_clause}:"]
        inner_start = len(block)
        for child in children_of.get(group.id, []):
            block.extend(emit_group(child, depth + 1))
            block.append("")
        for node in members_of.get(group.id, []):
            block.extend(f"{pad}{INDENT}{ln}" if ln else "" for ln in emit_node_lines(node))
            block.append("")
        while len(block) > inner_start and block[-1] == "":
            block.pop()
        if len(block) == inner_start:
            block.append(f"{pad}{INDENT}pass")
        return block

    lines: list[str] = []
    first = True
    for group in children_of.get(None, []):
        if not first:
            lines.append("")
        first = False
        lines.extend(emit_group(group, 0))
    for node in members_of.get(None, []):
        if not first:
            lines.append("")
        first = False
        lines.extend(f"{INDENT}{ln}" if ln else "" for ln in emit_node_lines(node))
    if not lines:
        lines.append(f"{INDENT}pass")
    return lines


def generate_source(graph: GraphModel, base_source: str | None = None) -> str:
    if base_source is not None:
        from dagsmith.core.transform import transform_source

        return transform_source(graph, base_source)

    validate_graph(graph)
    order = topo_order(graph)

    group_ids = {group.id for group in graph.groups}
    group_vars = {gid: group_var_name(gid) for gid in edge_group_endpoints(graph)}

    imports = {"from airflow.sdk import dag"}
    if any(node.block_id == "python" for node in order):
        imports = {"from airflow.sdk import dag, task"}
    for node in order:
        stmt = get_block(node.block_id).import_stmt
        if stmt:
            imports.add(stmt)

    meta = graph.dag
    if graph.groups:
        imports.add("from airflow.sdk import TaskGroup")
    if any(edge.label for edge in graph.edges):
        imports.add("from airflow.sdk import Label")
    if meta.start_date:
        imports.add("import pendulum")
    if meta.retry_delay_s is not None:
        imports.add("from datetime import timedelta")

    func_name = sanitize_identifier(meta.dag_id)
    dag_kwargs = []
    if func_name != meta.dag_id:
        dag_kwargs.append(f"dag_id={meta.dag_id!r}")
    dag_kwargs.append("schedule=" + (repr(meta.schedule) if meta.schedule else "None"))
    if meta.start_date:
        dag_kwargs.append(f"start_date={start_date_code(meta.start_date)}")
    if meta.catchup is not None:
        dag_kwargs.append(f"catchup={meta.catchup}")
    if meta.max_active_runs is not None:
        dag_kwargs.append(f"max_active_runs={meta.max_active_runs}")
    if meta.description:
        dag_kwargs.append(f"description={meta.description!r}")
    if meta.tags:
        dag_kwargs.append(f"tags={meta.tags!r}")
    defaults = default_args_code(meta)
    if defaults:
        dag_kwargs.append(f"default_args={defaults}")

    lines: list[str] = [
        "# dagsmith: v1",
        f'"""{meta.description or f"DAG {meta.dag_id} created with DagSmith."}"""',
        "",
        "from __future__ import annotations",
        "",
        *sorted(imports),
        "",
        "",
        f"@dag({', '.join(dag_kwargs)})",
        f"def {func_name}():",
    ]

    lines.extend(_emit_dag_body(graph, order, group_vars))

    def _endpoint_var(endpoint_id: str) -> str:
        if endpoint_id in group_ids:
            return group_vars.get(endpoint_id) or group_var_name(endpoint_id)
        return var_name(endpoint_id)

    if graph.edges:
        lines.append("")
        for edge in graph.edges:
            lines.append(
                f"{INDENT}"
                + dep_line(_endpoint_var(edge.source), _endpoint_var(edge.target), edge.label)
            )

    lines.extend(["", "", f"{func_name}()", ""])
    return "\n".join(lines)
