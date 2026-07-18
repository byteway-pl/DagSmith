"""Minimal, formatting-preserving edits of an existing DAG file (libcst).

Given the target graph and the current file, applies only the edits implied by
the semantic diff: add/remove task, change a parameter, change DAG meta, change
dependencies. Statements the diff does not touch stay byte-for-byte identical.
An unchanged graph short-circuits to ``base_source`` itself, which guarantees
the round-trip invariant.

Statements are addressed by paths (see ``parser.py``), so edits work inside
nested TaskGroup blocks as well.

Deliberate simplifications (documented in ARCHITECTURE.md):
- renaming a task is remove+add (its statement is regenerated),
- any change to dependencies rewrites the dependency lines canonically
  (``a >> b`` one per line, at the end of the DAG body),
- task groups are read-only containers: new tasks are added at the top level,
  group structure itself is editable only in code.
"""

from __future__ import annotations

import textwrap
from typing import Any

import libcst as cst

from dagsmith.core.catalog import get_block
from dagsmith.core.codegen import (
    INDENT,
    default_args_code,
    dep_line,
    edge_group_endpoints,
    emit_node_lines,
    group_var_name,
    param_literal,
    start_date_code,
    validate_graph,
    var_name,
)
from dagsmith.core.model import GraphModel, GraphValidationError, TaskNode
from dagsmith.core.parser import ParsedDag, Path, parse_source


def _norm_params(node: TaskNode) -> dict[str, Any]:
    if node.opaque or node.block_id == "opaque":
        return {}
    return {k: v for k, v in node.params.items() if v not in (None, "")}


def _node_key(node: TaskNode) -> tuple[Any, ...]:
    params = tuple(sorted(_norm_params(node).items()))
    return (node.id, node.block_id, params, bool(node.opaque), node.group_id)


def _meta_key(dag: GraphModel) -> tuple[Any, ...]:
    meta = dag.dag
    return (
        meta.dag_id,
        meta.schedule or None,
        meta.description or None,
        list(meta.tags),
        meta.start_date or None,
        meta.catchup,
        meta.max_active_runs,
        meta.owner or None,
        meta.email or None,
        meta.retries,
        meta.retry_delay_s,
    )


def _edge_key(graph: GraphModel) -> set[tuple[str, str, str | None]]:
    return {(e.source, e.target, e.label or None) for e in graph.edges}


def _graphs_equal(a: GraphModel, b: GraphModel) -> bool:
    if _meta_key(a) != _meta_key(b):
        return False
    if {_node_key(n) for n in a.nodes} != {_node_key(n) for n in b.nodes}:
        return False
    if {(g.id, g.parent_id) for g in a.groups} != {(g.id, g.parent_id) for g in b.groups}:
        return False
    return _edge_key(a) == _edge_key(b)


def _tight_equal() -> cst.AssignEqual:
    return cst.AssignEqual(
        whitespace_before=cst.SimpleWhitespace(""),
        whitespace_after=cst.SimpleWhitespace(""),
    )


def _updated_call(call: cst.Call, changes: dict[str, str | None]) -> cst.Call:
    """Apply kwarg-level changes: name -> literal code, or None to drop the kwarg."""
    new_args: list[cst.Arg] = []
    handled: set[str] = set()
    for arg in call.args:
        name = arg.keyword.value if arg.keyword else None
        if name is not None and name in changes:
            handled.add(name)
            code = changes[name]
            if code is None:
                continue
            new_args.append(arg.with_changes(value=cst.parse_expression(code)))
        else:
            new_args.append(arg)
    to_append = [
        (name, code)
        for name, code in changes.items()
        if name not in handled and code is not None
    ]
    if to_append:
        if new_args:
            new_args[-1] = new_args[-1].with_changes(
                comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
            )
        for position, (name, code) in enumerate(to_append):
            comma = (
                cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                if position < len(to_append) - 1
                else cst.MaybeSentinel.DEFAULT
            )
            new_args.append(
                cst.Arg(
                    keyword=cst.Name(name),
                    value=cst.parse_expression(code),
                    equal=_tight_equal(),
                    comma=comma,
                )
            )
    if new_args and isinstance(new_args[-1].comma, cst.Comma):
        new_args[-1] = new_args[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)
    return call.with_changes(args=new_args)


def _param_changes(old: TaskNode, new: TaskNode) -> dict[str, str | None]:
    block = get_block(new.block_id)
    types = {p.name: p.type for p in block.params}
    old_params = _norm_params(old)
    new_params = _norm_params(new)
    changes: dict[str, str | None] = {}
    for name in set(old_params) | set(new_params):
        if name not in types or old_params.get(name) == new_params.get(name):
            continue
        if name not in new_params:
            changes[name] = None
        else:
            changes[name] = param_literal(new_params[name], types[name])
    return changes


def _parse_statements(code_lines: list[str]) -> list[cst.BaseStatement]:
    module = cst.parse_module("\n".join(code_lines) + "\n")
    return list(module.body)


def _with_blank_line(stmt: cst.BaseStatement) -> cst.BaseStatement:
    return stmt.with_changes(leading_lines=[cst.EmptyLine(), *stmt.leading_lines])


def _rewrite_operator_stmt(
    stmt: cst.BaseStatement, changes: dict[str, str | None]
) -> cst.BaseStatement:
    assert isinstance(stmt, cst.SimpleStatementLine)
    small = stmt.body[0]
    assert isinstance(small, cst.Assign) and isinstance(small.value, cst.Call)
    return stmt.with_changes(
        body=[small.with_changes(value=_updated_call(small.value, changes))]
    )


def _rewrite_python_stmt(
    stmt: cst.BaseStatement, old: TaskNode, new: TaskNode
) -> cst.BaseStatement:
    assert isinstance(stmt, cst.FunctionDef)
    func = stmt

    if (old.params.get("body") or "") != (new.params.get("body") or ""):
        body_text = str(new.params.get("body") or "pass")
        holder = cst.parse_statement(
            "def _dagsmith_tmp():\n" + textwrap.indent(body_text, INDENT)
        )
        assert isinstance(holder, cst.FunctionDef)
        func = func.with_changes(body=holder.body)

    decorator_changes = _param_changes(
        TaskNode(
            id=old.id,
            block_id="python",
            params={k: v for k, v in old.params.items() if k != "body"},
        ),
        TaskNode(
            id=new.id,
            block_id="python",
            params={k: v for k, v in new.params.items() if k != "body"},
        ),
    )
    if decorator_changes:
        new_decorators: list[cst.Decorator] = []
        for decorator in func.decorators:
            target = decorator.decorator
            is_task = (isinstance(target, cst.Name) and target.value == "task") or (
                isinstance(target, cst.Call)
                and isinstance(target.func, cst.Name)
                and target.func.value == "task"
            )
            if not is_task:
                new_decorators.append(decorator)
                continue
            call = target if isinstance(target, cst.Call) else cst.Call(func=cst.Name("task"))
            call = _updated_call(call, decorator_changes)
            new_decorators.append(
                decorator.with_changes(decorator=cst.Name("task") if not call.args else call)
            )
        func = func.with_changes(decorators=new_decorators)
    return func


def _meta_changes(
    parsed: ParsedDag, graph: GraphModel, func_name: str | None
) -> dict[str, str | None]:
    old, new = parsed.graph.dag, graph.dag
    changes: dict[str, str | None] = {}
    if (old.schedule or None) != (new.schedule or None):
        changes["schedule"] = repr(new.schedule) if new.schedule else "None"
    if (old.description or None) != (new.description or None):
        changes["description"] = repr(new.description) if new.description else None
    if list(old.tags) != list(new.tags):
        changes["tags"] = repr(list(new.tags)) if new.tags else None
    if (old.start_date or None) != (new.start_date or None):
        changes["start_date"] = start_date_code(new.start_date) if new.start_date else None
    if old.catchup != new.catchup:
        changes["catchup"] = str(new.catchup) if new.catchup is not None else None
    if old.max_active_runs != new.max_active_runs:
        changes["max_active_runs"] = (
            str(new.max_active_runs) if new.max_active_runs is not None else None
        )
    old_defaults = (old.owner, old.email, old.retries, old.retry_delay_s)
    new_defaults = (new.owner, new.email, new.retries, new.retry_delay_s)
    if old_defaults != new_defaults:
        changes["default_args"] = default_args_code(new, parsed.default_args_extras)
    if old.dag_id != new.dag_id:
        if func_name is not None and new.dag_id == func_name:
            changes["dag_id"] = None
        else:
            changes["dag_id"] = repr(new.dag_id)
    return changes


def _apply_meta(container: cst.CSTNode, changes: dict[str, str | None]) -> cst.CSTNode:
    if isinstance(container, cst.FunctionDef):
        new_decorators: list[cst.Decorator] = []
        for decorator in container.decorators:
            target = decorator.decorator
            is_dag = (isinstance(target, cst.Name) and target.value == "dag") or (
                isinstance(target, cst.Call)
                and isinstance(target.func, cst.Name)
                and target.func.value == "dag"
            )
            if not is_dag:
                new_decorators.append(decorator)
                continue
            call = target if isinstance(target, cst.Call) else cst.Call(func=cst.Name("dag"))
            call = _updated_call(call, changes)
            new_decorators.append(
                decorator.with_changes(decorator=cst.Name("dag") if not call.args else call)
            )
        return container.with_changes(decorators=new_decorators)

    assert isinstance(container, cst.With)
    new_items = []
    for item in container.items:
        call = item.item
        if (
            isinstance(call, cst.Call)
            and isinstance(call.func, cst.Name)
            and call.func.value == "DAG"
        ):
            local = dict(changes)
            if "dag_id" in local and call.args and call.args[0].keyword is None:
                code = local.pop("dag_id")
                if code is not None:
                    args = list(call.args)
                    args[0] = args[0].with_changes(value=cst.parse_expression(code))
                    call = call.with_changes(args=args)
            call = _updated_call(call, local)
            item = item.with_changes(item=call)
        new_items.append(item)
    return container.with_changes(items=new_items)


# -- path-based statement surgery -----------------------------------------


def _add_asname(with_stmt: cst.BaseStatement, var: str) -> cst.BaseStatement:
    """Add ``as VAR`` to the TaskGroup item of a ``with TaskGroup(...):`` block."""
    assert isinstance(with_stmt, cst.With)
    new_items = []
    for item in with_stmt.items:
        call = item.item
        if (
            isinstance(call, cst.Call)
            and isinstance(call.func, cst.Name)
            and call.func.value == "TaskGroup"
            and item.asname is None
        ):
            item = item.with_changes(asname=cst.AsName(name=cst.Name(var)))
        new_items.append(item)
    return with_stmt.with_changes(items=new_items)


def _stmt_at(block: cst.IndentedBlock, path: Path) -> cst.BaseStatement:
    stmt: cst.BaseStatement = block.body[path[0]]
    for index in path[1:]:
        assert isinstance(stmt, cst.With)
        inner = stmt.body
        assert isinstance(inner, cst.IndentedBlock)
        stmt = inner.body[index]
    return stmt


def _rebuild_children(
    stmts: list[cst.BaseStatement],
    prefix: Path,
    deleted: set[Path],
    replacements: dict[Path, cst.BaseStatement],
    touched_prefixes: set[Path],
    insertions: dict[Path, list[cst.BaseStatement]],
) -> list[cst.BaseStatement]:
    result: list[cst.BaseStatement] = []
    for index, stmt in enumerate(stmts):
        path = (*prefix, index)
        if path in deleted:
            continue
        stmt = replacements.get(path, stmt)
        if isinstance(stmt, cst.With) and path in touched_prefixes:
            inner = stmt.body
            if isinstance(inner, cst.IndentedBlock):
                children = _rebuild_children(
                    list(inner.body), path, deleted, replacements, touched_prefixes, insertions
                )
                children.extend(insertions.get(path, []))
                if not children:
                    children = _parse_statements(["pass"])
                stmt = stmt.with_changes(body=inner.with_changes(body=children))
        result.append(stmt)
    return result


def _ensure_import(module: cst.Module, symbol: str, import_stmt: str) -> cst.Module:
    """Insert ``import_stmt`` after the last import unless ``symbol`` is imported."""
    last_import = -1
    for index, stmt in enumerate(module.body):
        if isinstance(stmt, cst.SimpleStatementLine) and any(
            isinstance(small, (cst.Import, cst.ImportFrom)) for small in stmt.body
        ):
            if symbol in module.code_for_node(stmt):
                return module
            last_import = index
    new_import = cst.parse_statement(import_stmt + "\n")
    body = list(module.body)
    body.insert(last_import + 1, new_import)
    return module.with_changes(body=body)


def transform_source(graph: GraphModel, base_source: str) -> str:
    validate_graph(graph, allow_opaque=True)
    parsed = parse_source(base_source)

    if _graphs_equal(graph, parsed.graph):
        return base_source

    base_by_id = {node.id: node for node in parsed.graph.nodes}
    new_by_id = {node.id: node for node in graph.nodes}
    removed = set(base_by_id) - set(new_by_id)
    added = [node for node in graph.nodes if node.id not in base_by_id]
    for node in added:
        if node.opaque or node.block_id == "opaque":
            raise GraphValidationError(
                f"Cannot create opaque task {node.id!r} visually — edit the code instead"
            )

    # -- group diff --------------------------------------------------------
    base_group_ids = {g.id for g in parsed.graph.groups}
    new_group_ids = {g.id for g in graph.groups}
    added_groups = [g for g in graph.groups if g.id not in base_group_ids]
    removed_groups = base_group_ids - new_group_ids

    def _in_removed_subtree(group_id: str | None) -> bool:
        return group_id is not None and any(
            group_id == g or group_id.startswith(f"{g}.") for g in removed_groups
        )

    for group in added_groups:
        if group.parent_id is not None and (
            group.parent_id not in base_group_ids or group.parent_id in removed_groups
        ):
            raise GraphValidationError(
                f"New group {group.id!r}: nesting under another new group is not supported"
            )
    for node in graph.nodes:
        if node.group_id and node.group_id not in new_group_ids:
            raise GraphValidationError(
                f"Task {node.id!r} references unknown group {node.group_id!r}"
            )
    # Removing a group relocates its surviving tasks; code-only blocks inside
    # a removed group cannot be relocated, so the removal must happen in code.
    for node in parsed.graph.nodes:
        if (
            _in_removed_subtree(node.group_id)
            and node.opaque
            and node.id in new_by_id
        ):
            raise GraphValidationError(
                f"Group {node.group_id!r} contains code-only block {node.id!r} — "
                "remove the group in the Code view"
            )

    moved = [
        node_id
        for node_id, new_node in new_by_id.items()
        if node_id in base_by_id and base_by_id[node_id].group_id != new_node.group_id
    ]
    for node_id in moved:
        if base_by_id[node_id].opaque:
            raise GraphValidationError(
                f"Code-only block {node_id!r} can be moved between groups only in code"
            )

    edges_changed = _edge_key(parsed.graph) != _edge_key(graph)
    # Relocated definitions may end up after existing dependency lines, so any
    # membership change canonicalizes the dependency section too.
    deps_rewrite = edges_changed or bool(moved)

    container = parsed.module.body[parsed.container_index]
    body_block = container.body
    assert isinstance(body_block, cst.IndentedBlock)

    deleted: set[Path] = set()
    replacements: dict[Path, cst.BaseStatement] = {}

    for node_id in removed:
        binding = parsed.bindings[node_id]
        for path in (binding.def_path, binding.call_path):
            if path is not None:
                deleted.add(path)

    for node_id, new_node in new_by_id.items():
        old_node = base_by_id.get(node_id)
        if old_node is None or old_node.opaque:
            continue
        binding = parsed.bindings[node_id]
        if binding.def_path is None:
            continue
        if new_node.block_id != old_node.block_id:
            raise GraphValidationError(
                f"Task {node_id!r}: changing block type is not supported — delete and re-add"
            )
        stmt = _stmt_at(body_block, binding.def_path)
        if new_node.block_id == "python":
            if _norm_params(old_node) != _norm_params(new_node):
                replacements[binding.def_path] = _rewrite_python_stmt(
                    stmt, old_node, new_node
                )
        else:
            changes = _param_changes(old_node, new_node)
            if changes:
                replacements[binding.def_path] = _rewrite_operator_stmt(stmt, changes)

    if deps_rewrite:
        deleted.update(parsed.dep_paths)

    # Removed groups: delete their `with TaskGroup(...)` statements. Surviving
    # member tasks changed group_id, so the move logic below relocates their
    # statements (captured from the original tree before the rebuild).
    for group_id in removed_groups:
        path = parsed.group_paths.get(group_id)
        if path is not None:
            deleted.add(path)

    # Groups used as dependency endpoints need an `as VAR` binding. Reuse the
    # existing one, or add it to the group's `with` block (added groups get it
    # at emission time below).
    group_var_map: dict[str, str] = {}
    for group_id in edge_group_endpoints(graph):
        existing_var = parsed.group_vars.get(group_id)
        group_var_map[group_id] = existing_var or group_var_name(group_id)
        if (
            existing_var is None
            and group_id in parsed.group_paths
            and group_id not in removed_groups
        ):
            path = parsed.group_paths[group_id]
            base_stmt = replacements.get(path) or _stmt_at(body_block, path)
            replacements[path] = _add_asname(base_stmt, group_var_map[group_id])

    # -- routing of relocated / new statements -----------------------------
    insertions: dict[Path, list[cst.BaseStatement]] = {}
    appended: list[cst.BaseStatement] = []
    new_group_members: dict[str, list[cst.BaseStatement]] = {}

    def _route(group_id: str | None, stmts: list[cst.BaseStatement]) -> None:
        if not stmts:
            return
        if group_id is None:
            appended.extend(stmts)
        elif group_id in parsed.group_paths:
            insertions.setdefault(parsed.group_paths[group_id], []).extend(stmts)
        else:
            new_group_members.setdefault(group_id, []).extend(stmts)

    # Moves between groups: relocate the original statements verbatim.
    for node_id in moved:
        binding = parsed.bindings[node_id]
        stmts_to_move: list[cst.BaseStatement] = []
        for path in (binding.def_path, binding.call_path):
            if path is None:
                continue
            stmt = replacements.pop(path, None) or _stmt_at(body_block, path)
            deleted.add(path)
            stmts_to_move.append(stmt)
        _route(new_by_id[node_id].group_id, stmts_to_move)

    for node in added:
        stmts = _parse_statements(emit_node_lines(node))
        if stmts:
            stmts[0] = _with_blank_line(stmts[0])
        _route(node.group_id, stmts)

    def _existing_var(node_id: str) -> str | None:
        binding = parsed.bindings.get(node_id)
        if binding is None or not binding.var_names:
            return None
        return binding.var_names[0]

    # New TaskGroup blocks (top-level or nested under an existing group).
    for group in added_groups:
        local = group.id.split(".")[-1]
        as_clause = f" as {group_var_map[group.id]}" if group.id in group_var_map else ""
        holder = cst.parse_statement(f"with TaskGroup({local!r}){as_clause}:\n    pass")
        assert isinstance(holder, cst.With)
        members = new_group_members.pop(group.id, [])
        if members:
            inner = holder.body
            assert isinstance(inner, cst.IndentedBlock)
            holder = holder.with_changes(body=inner.with_changes(body=members))
        holder_stmt = _with_blank_line(holder)
        if group.parent_id is not None:
            insertions.setdefault(parsed.group_paths[group.parent_id], []).append(holder_stmt)
        else:
            appended.append(holder_stmt)
    if new_group_members:
        raise GraphValidationError(
            f"Tasks assigned to unknown groups: {sorted(new_group_members)}"
        )

    if deps_rewrite:
        # Taskflow nodes previously instantiated only inside a chain need an
        # explicit `var = func()` once the chains are regenerated. Must come
        # after any group block that (now) contains the function definition.
        for node in graph.nodes:
            binding = parsed.bindings.get(node.id)
            if (
                binding is not None
                and binding.func_name is not None
                and binding.inline_call_only
            ):
                line = f"{var_name(node.id)} = {binding.func_name}()"
                appended.extend(_parse_statements([line]))
                binding.var_names.append(var_name(node.id))

    def _endpoint_var(endpoint_id: str) -> str:
        if endpoint_id in new_group_ids:
            return group_var_map.get(endpoint_id) or group_var_name(endpoint_id)
        return _existing_var(endpoint_id) or var_name(endpoint_id)

    if deps_rewrite and graph.edges:
        lines = [
            dep_line(_endpoint_var(e.source), _endpoint_var(e.target), e.label)
            for e in graph.edges
        ]
        stmts = _parse_statements(lines)
        if stmts:
            stmts[0] = _with_blank_line(stmts[0])
        appended.extend(stmts)

    touched_prefixes = {
        path[:length]
        for path in (set(deleted) | set(replacements))
        for length in range(1, len(path))
    }
    for insertion_path in insertions:
        for length in range(1, len(insertion_path) + 1):
            touched_prefixes.add(insertion_path[:length])

    new_body = _rebuild_children(
        list(body_block.body), (), deleted, replacements, touched_prefixes, insertions
    )
    new_body.extend(appended)
    if not new_body:
        new_body = _parse_statements(["pass"])

    new_container = container.with_changes(body=body_block.with_changes(body=new_body))

    meta_changes = _meta_changes(
        parsed,
        graph,
        container.name.value if isinstance(container, cst.FunctionDef) else None,
    )
    if meta_changes:
        new_container = _apply_meta(new_container, meta_changes)

    new_module_body = list(parsed.module.body)
    new_module_body[parsed.container_index] = new_container  # type: ignore[assignment]
    new_module = parsed.module.with_changes(body=new_module_body)
    # Newly added operator tasks need their class imported, else the file fails
    # import validation. @task nodes need `task` from airflow.sdk.
    for node in added:
        if node.opaque:
            continue
        block = get_block(node.block_id)
        if block.import_stmt and block.class_name:
            new_module = _ensure_import(new_module, block.class_name, block.import_stmt)
        if node.block_id == "python":
            new_module = _ensure_import(new_module, "task", "from airflow.sdk import task")
    if added_groups:
        new_module = _ensure_import(new_module, "TaskGroup", "from airflow.sdk import TaskGroup")
    if deps_rewrite and any(e.label for e in graph.edges):
        new_module = _ensure_import(new_module, "Label", "from airflow.sdk import Label")
    if meta_changes.get("start_date"):
        new_module = _ensure_import(new_module, "pendulum", "import pendulum")
    if "timedelta" in (meta_changes.get("default_args") or ""):
        new_module = _ensure_import(
            new_module, "timedelta", "from datetime import timedelta"
        )
    return new_module.code


__all__ = ["transform_source"]
