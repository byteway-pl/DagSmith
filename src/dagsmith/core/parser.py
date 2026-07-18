"""Python source -> GraphModel via libcst (lossless, formatting-preserving).

Supported (tiers T1/T2/T3, see ARCHITECTURE.md §4.5):
- ``@dag(...)``-decorated function or top-level ``with DAG(...):`` block
  (multiple DAGs in one file: the first one is edited, with a warning),
- operator instantiations assigned to variables (known blocks -> typed nodes,
  anything else -> opaque nodes),
- ``@task``-decorated functions (+ their call sites, incl. ``.expand(...)``),
- dynamic task mapping ``Op.partial(...).expand(...)`` -> opaque node,
- ``with TaskGroup(...):`` blocks, nested -> groups + node.group_id,
- loops / conditionals inside the DAG body -> opaque "code block" regions,
- dependencies via ``>>`` / ``<<`` chains, lists, and ``chain(...)``.

Statements are addressed by *paths* (indices through nested indented blocks) so
``transform.py`` can apply minimal edits inside task groups too.
"""

from __future__ import annotations

import ast as pyast
import textwrap
from dataclasses import dataclass, field
from typing import Any

import libcst as cst

from dagsmith.core.model import (
    AIRFLOW_ID_RE,
    DagMeta,
    Edge,
    GraphModel,
    TaskGroupNode,
    TaskNode,
)

# Params understood on the @task decorator (the python block).
PYTHON_DECORATOR_PARAMS = {"retries", "trigger_rule"}


def _resolve_block(class_name: str | None):
    """Operator class name -> BlockDef (builtin or provider catalog), or None."""
    if not class_name:
        return None
    try:
        from dagsmith.core.catalog import block_by_class_name

        return block_by_class_name(class_name)
    except Exception:
        return None

Path = tuple[int, ...]


class ParseError(ValueError):
    pass


@dataclass
class TaskBinding:
    node: TaskNode
    def_path: Path | None = None  # path of the defining statement in the dag body
    call_path: Path | None = None  # taskflow: path of the `var = func()` statement
    var_names: list[str] = field(default_factory=list)
    func_name: str | None = None  # taskflow function name
    inline_call_only: bool = False  # taskflow instantiated only inside a dep chain


@dataclass
class ParsedDag:
    module: cst.Module
    graph: GraphModel
    warnings: list[str]
    style: str  # "decorator" | "with"
    container_index: int
    bindings: dict[str, TaskBinding]
    dep_paths: list[Path]
    var_to_node: dict[str, str]
    # Path of each `with TaskGroup(...)` statement, keyed by full group id.
    group_paths: dict[str, Path] = field(default_factory=dict)
    # Variable each group is bound to via `as VAR` (only when present in code).
    group_vars: dict[str, str] = field(default_factory=dict)
    # Entries of an existing default_args dict that DagSmith does not model,
    # as raw (key_code, value_code) pairs — preserved on rewrite.
    default_args_extras: list[tuple[str, str]] = field(default_factory=list)


def _code(module: cst.Module, node: cst.CSTNode) -> str:
    return module.code_for_node(node)


def _literal(module: cst.Module, node: cst.BaseExpression) -> tuple[bool, Any]:
    try:
        return True, pyast.literal_eval(_code(module, node).strip())
    except Exception:
        return False, None


def _call_kwargs(call: cst.Call) -> dict[str, cst.Arg]:
    return {arg.keyword.value: arg for arg in call.args if arg.keyword is not None}


def _decorator_named(func: cst.FunctionDef, name: str) -> cst.Decorator | None:
    for decorator in func.decorators:
        target = decorator.decorator
        if isinstance(target, cst.Name) and target.value == name:
            return decorator
        if (
            isinstance(target, cst.Call)
            and isinstance(target.func, cst.Name)
            and target.func.value == name
        ):
            return decorator
    return None


def _call_chain_base(expr: cst.BaseExpression) -> tuple[str | None, list[cst.Call]]:
    """For `X.partial(a).expand(b)` return ("X", [partial_call, expand_call])."""
    calls: list[cst.Call] = []
    current: cst.BaseExpression = expr
    while isinstance(current, cst.Call):
        calls.append(current)
        func = current.func
        if isinstance(func, cst.Name):
            return func.value, list(reversed(calls))
        if isinstance(func, cst.Attribute):
            current = func.value
        else:
            return None, list(reversed(calls))
    if isinstance(current, cst.Name):
        return current.value, list(reversed(calls))
    return None, list(reversed(calls))


def _find_containers(module: cst.Module) -> list[tuple[str, int, cst.CSTNode]]:
    found: list[tuple[str, int, cst.CSTNode]] = []
    for index, stmt in enumerate(module.body):
        if isinstance(stmt, cst.FunctionDef) and _decorator_named(stmt, "dag") is not None:
            found.append(("decorator", index, stmt))
        elif isinstance(stmt, cst.With):
            for item in stmt.items:
                call = item.item
                if (
                    isinstance(call, cst.Call)
                    and isinstance(call.func, cst.Name)
                    and call.func.value == "DAG"
                ):
                    found.append(("with", index, stmt))
                    break
    return found


def _parse_start_date(module: cst.Module, expr: cst.BaseExpression) -> str | None:
    """`pendulum.datetime(y, m, d, ...)` / `datetime(y, m, d)` / "YYYY-MM-DD" -> ISO date."""
    ok, value = _literal(module, expr)
    if ok and isinstance(value, str) and len(value) >= 10:
        return value[:10]
    if isinstance(expr, cst.Call):
        func_name = None
        if isinstance(expr.func, cst.Name):
            func_name = expr.func.value
        elif isinstance(expr.func, cst.Attribute):
            func_name = expr.func.attr.value
        if func_name == "datetime":
            numbers: list[int] = []
            for arg in expr.args:
                if arg.keyword is not None:
                    break
                arg_ok, arg_value = _literal(module, arg.value)
                if not arg_ok or not isinstance(arg_value, int):
                    break
                numbers.append(arg_value)
            if len(numbers) >= 3:
                return f"{numbers[0]:04d}-{numbers[1]:02d}-{numbers[2]:02d}"
    return None


def _parse_retry_delay(module: cst.Module, expr: cst.BaseExpression) -> int | None:
    ok, value = _literal(module, expr)
    if ok and isinstance(value, (int, float)):
        return int(value)
    if isinstance(expr, cst.Call):
        func = expr.func
        name = func.value if isinstance(func, cst.Name) else (
            func.attr.value if isinstance(func, cst.Attribute) else None
        )
        if name == "timedelta":
            seconds = 0
            factors = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
            for arg in expr.args:
                if arg.keyword is None or arg.keyword.value not in factors:
                    return None
                arg_ok, arg_value = _literal(module, arg.value)
                if not arg_ok or not isinstance(arg_value, (int, float)):
                    return None
                seconds += int(arg_value) * factors[arg.keyword.value]
            return seconds
    return None


_DEFAULT_ARG_KEYS = ("owner", "email", "retries", "retry_delay")


def _parse_default_args(
    module: cst.Module, expr: cst.BaseExpression, warnings: list[str]
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Split a default_args dict into modeled fields + preserved raw extras."""
    fields: dict[str, Any] = {}
    extras: list[tuple[str, str]] = []
    if not isinstance(expr, cst.Dict):
        warnings.append("default_args is not a dict literal — editable only in code")
        return fields, extras
    for element in expr.elements:
        if not isinstance(element, cst.DictElement):
            warnings.append("default_args uses ** expansion — extra entries preserved as-is")
            continue
        key_code = _code(module, element.key).strip()
        value_code = _code(module, element.value).strip()
        ok, key = _literal(module, element.key)
        if not ok or not isinstance(key, str) or key not in _DEFAULT_ARG_KEYS:
            extras.append((key_code, value_code))
            continue
        if key == "retry_delay":
            delay = _parse_retry_delay(module, element.value)
            if delay is None:
                extras.append((key_code, value_code))
            else:
                fields["retry_delay_s"] = delay
            continue
        value_ok, value = _literal(module, element.value)
        if not value_ok:
            extras.append((key_code, value_code))
            continue
        if (key in ("owner", "email") and isinstance(value, str)) or (
            key == "retries" and isinstance(value, int)
        ):
            fields[key] = value
        else:
            extras.append((key_code, value_code))
    return fields, extras


def _meta_from_call(
    module: cst.Module, call: cst.Call | None, fallback_dag_id: str | None, warnings: list[str]
) -> tuple[DagMeta, list[tuple[str, str]]]:
    dag_id = fallback_dag_id
    meta_kwargs: dict[str, Any] = {}
    extras: list[tuple[str, str]] = []
    if call is not None:
        for position, arg in enumerate(call.args):
            name = arg.keyword.value if arg.keyword else None
            if name is None and position == 0:
                name = "dag_id"
            if name == "start_date":
                start_date = _parse_start_date(module, arg.value)
                if start_date is None:
                    warnings.append("start_date is not a recognizable date — left as-is")
                else:
                    meta_kwargs["start_date"] = start_date
                continue
            if name == "default_args":
                fields, extras = _parse_default_args(module, arg.value, warnings)
                meta_kwargs.update(fields)
                continue
            if name not in (
                "dag_id",
                "schedule",
                "description",
                "tags",
                "catchup",
                "max_active_runs",
            ):
                continue
            ok, value = _literal(module, arg.value)
            if not ok:
                warnings.append(f"DAG parameter {name!r} is not a literal — left as-is")
                continue
            if name == "dag_id" and isinstance(value, str):
                dag_id = value
            elif name == "schedule":
                meta_kwargs["schedule"] = value if isinstance(value, str) else None
            elif name == "description" and isinstance(value, str):
                meta_kwargs["description"] = value
            elif name == "tags" and isinstance(value, (list, tuple)):
                meta_kwargs["tags"] = [str(tag) for tag in value]
            elif name == "catchup" and isinstance(value, bool):
                meta_kwargs["catchup"] = value
            elif name == "max_active_runs" and isinstance(value, int):
                meta_kwargs["max_active_runs"] = value
    if not dag_id or not AIRFLOW_ID_RE.match(dag_id):
        raise ParseError(f"Cannot determine a valid dag_id (got {dag_id!r})")
    return DagMeta(dag_id=dag_id, **meta_kwargs), extras


def _params_from_call(
    module: cst.Module, call: cst.Call, block: Any, warnings: list[str]
) -> dict[str, Any]:
    param_types = {p.name: p.type for p in block.params}
    params: dict[str, Any] = {}
    for name, arg in _call_kwargs(call).items():
        if name == "task_id" or name not in param_types:
            continue
        if param_types[name] in ("python", "dict"):
            # Raw expression params (callables, dicts) round-trip as source text.
            params[name] = _code(module, arg.value).strip()
            continue
        ok, value = _literal(module, arg.value)
        if ok:
            params[name] = value
        else:
            warnings.append(f"Parameter {name!r} is not a literal — editable only in code")
    return params


def _taskflow_body(module: cst.Module, func: cst.FunctionDef) -> str:
    return textwrap.dedent(_code(module, func.body)).strip("\n")


def _chain_terms(expr: cst.BaseExpression) -> list[tuple[str, cst.BaseExpression]] | None:
    """Flatten `a >> b << c` into [("", a), (">>", b), ("<<", c)]; None if not a chain."""
    if isinstance(expr, cst.BinaryOperation) and isinstance(
        expr.operator, (cst.RightShift, cst.LeftShift)
    ):
        left = _chain_terms(expr.left)
        if left is None:
            left = [("", expr.left)]
        op = ">>" if isinstance(expr.operator, cst.RightShift) else "<<"
        return [*left, (op, expr.right)]
    return None


def _taskgroup_call(stmt: cst.With) -> cst.Call | None:
    for item in stmt.items:
        call = item.item
        if (
            isinstance(call, cst.Call)
            and isinstance(call.func, cst.Name)
            and call.func.value == "TaskGroup"
        ):
            return call
    return None


class _GraphBuilder:
    def __init__(self, module: cst.Module) -> None:
        self.module = module
        self.warnings: list[str] = []
        self.bindings: dict[str, TaskBinding] = {}
        self.var_to_node: dict[str, str] = {}
        self.func_to_node: dict[str, str] = {}
        self.dep_paths: list[Path] = []
        self.edges: list[Edge] = []
        self.order: list[str] = []
        self.groups: list[TaskGroupNode] = []
        self.group_paths: dict[str, Path] = {}
        # Variable a group is bound to via `with TaskGroup(...) as VAR:`.
        self.group_vars: dict[str, str] = {}
        self.var_to_group: dict[str, str] = {}
        self._region_count = 0

    # -- registration ------------------------------------------------------

    def _add(self, binding: TaskBinding) -> None:
        node_id = binding.node.id
        if node_id in self.bindings:
            self.warnings.append(f"Duplicate task id {node_id!r} — keeping the first one")
            return
        self.bindings[node_id] = binding
        self.order.append(node_id)
        for var in binding.var_names:
            self.var_to_node[var] = node_id
        if binding.func_name:
            self.func_to_node[binding.func_name] = node_id

    def _add_region(self, path: Path, stmt: cst.CSTNode, group_id: str | None) -> None:
        self._region_count += 1
        node_id = f"code_block_{self._region_count}"
        code = _code(self.module, stmt).strip()
        first_line = code.splitlines()[0] if code else "?"
        node = TaskNode(
            id=node_id,
            block_id="opaque",
            params={"code": code, "summary": first_line},
            opaque=True,
            group_id=group_id,
        )
        self._add(TaskBinding(node=node, def_path=path))
        self.warnings.append(
            f"Dynamic construct ({first_line[:60]!r}) shown as a code-only block"
        )

    # -- statement walk ----------------------------------------------------

    def walk(self, body: cst.IndentedBlock, prefix: Path, group_id: str | None) -> None:
        for index, stmt in enumerate(body.body):
            self.visit_statement((*prefix, index), stmt, group_id)

    def visit_statement(self, path: Path, stmt: cst.CSTNode, group_id: str | None) -> None:
        if isinstance(stmt, cst.FunctionDef):
            self._visit_funcdef(path, stmt, group_id)
            return
        if isinstance(stmt, cst.With):
            call = _taskgroup_call(stmt)
            if call is not None:
                self._visit_taskgroup(path, stmt, call, group_id)
            else:
                self._add_region(path, stmt, group_id)
            return
        if isinstance(stmt, (cst.For, cst.While, cst.If, cst.Try)):
            self._add_region(path, stmt, group_id)
            return
        if not isinstance(stmt, cst.SimpleStatementLine) or len(stmt.body) != 1:
            return
        small = stmt.body[0]
        if isinstance(small, cst.Assign) and isinstance(small.value, cst.Call):
            targets = [
                t.target.value for t in small.targets if isinstance(t.target, cst.Name)
            ]
            self._visit_call_assign(path, small.value, targets, group_id)
        elif isinstance(small, cst.Expr):
            self._visit_expr(path, small.value)

    def _visit_taskgroup(
        self, path: Path, stmt: cst.With, call: cst.Call, parent: str | None
    ) -> None:
        local_id: str | None = None
        kwargs = _call_kwargs(call)
        if call.args and call.args[0].keyword is None:
            ok, value = _literal(self.module, call.args[0].value)
            if ok and isinstance(value, str):
                local_id = value
        if local_id is None and "group_id" in kwargs:
            ok, value = _literal(self.module, kwargs["group_id"].value)
            if ok and isinstance(value, str):
                local_id = value
        if local_id is None:
            self._add_region(path, stmt, parent)
            return
        full_id = f"{parent}.{local_id}" if parent else local_id
        self.groups.append(TaskGroupNode(id=full_id, label=local_id, parent_id=parent))
        self.group_paths[full_id] = path
        # `with TaskGroup(...) as VAR:` — VAR can be a dependency endpoint.
        for item in stmt.items:
            if item.item is call and item.asname is not None:
                target = item.asname.name
                if isinstance(target, cst.Name):
                    self.group_vars[full_id] = target.value
                    self.var_to_group[target.value] = full_id
        if isinstance(stmt.body, cst.IndentedBlock):
            self.walk(stmt.body, path, full_id)

    def _visit_funcdef(self, path: Path, func: cst.FunctionDef, group_id: str | None) -> None:
        decorator = _decorator_named(func, "task")
        if decorator is None:
            self.warnings.append(
                f"Function {func.name.value!r} inside the DAG is not a @task — ignored"
            )
            return
        params: dict[str, Any] = {"body": _taskflow_body(self.module, func)}
        task_id = func.name.value
        if isinstance(decorator.decorator, cst.Call):
            for name, arg in _call_kwargs(decorator.decorator).items():
                ok, value = _literal(self.module, arg.value)
                if name == "task_id" and ok and isinstance(value, str):
                    task_id = value
                elif name in PYTHON_DECORATOR_PARAMS and ok:
                    params[name] = value
        node = TaskNode(id=task_id, block_id="python", params=params, group_id=group_id)
        self._add(
            TaskBinding(
                node=node,
                def_path=path,
                func_name=func.name.value,
                inline_call_only=True,  # until we see a call assignment
            )
        )

    def _visit_call_assign(
        self, path: Path, call: cst.Call, targets: list[str], group_id: str | None
    ) -> None:
        base_name, chain_calls = _call_chain_base(call)

        # `t = my_taskflow_func()` / `t = my_taskflow_func.expand(...)`
        if base_name in self.func_to_node:
            binding = self.bindings[self.func_to_node[base_name]]
            binding.call_path = path
            binding.var_names.extend(targets)
            binding.inline_call_only = False
            for var in targets:
                self.var_to_node[var] = binding.node.id
            return

        # task_id may live on any call in the chain (e.g. .partial(task_id=...)).
        task_id: str | None = None
        for chain_call in chain_calls:
            kwargs = _call_kwargs(chain_call)
            if "task_id" in kwargs:
                ok, value = _literal(self.module, kwargs["task_id"].value)
                if ok and isinstance(value, str):
                    task_id = value
                    break

        is_plain_call = isinstance(call.func, cst.Name)
        block = _resolve_block(base_name) if is_plain_call else None
        if block is not None and block.class_name is not None and task_id is not None:
            node = TaskNode(
                id=task_id,
                block_id=block.block_id,
                params=_params_from_call(self.module, call, block, self.warnings),
                group_id=group_id,
            )
            self._add(TaskBinding(node=node, def_path=path, var_names=targets))
            return

        # Anything else that looks like a task instantiation -> opaque node
        # (unknown operator, Op.partial(...).expand(...), helper call, ...).
        if task_id is not None or targets:
            node_id = task_id or targets[0]
            if not AIRFLOW_ID_RE.match(node_id):
                self.warnings.append("Skipped an unrecognized assignment")
                return
            node = TaskNode(
                id=node_id,
                block_id="opaque",
                params={"code": _code(self.module, call).strip()},
                opaque=True,
                group_id=group_id,
            )
            self._add(TaskBinding(node=node, def_path=path, var_names=targets))
            self.warnings.append(
                f"Task {node_id!r} uses an unsupported construct — editable only in code"
            )

    # -- dependencies ------------------------------------------------------

    def _resolve_operand(self, operand: cst.BaseExpression) -> list[str]:
        if isinstance(operand, cst.Name):
            # A dependency endpoint can be a task variable or a TaskGroup variable.
            node_id = self.var_to_node.get(operand.value) or self.var_to_group.get(
                operand.value
            )
            if node_id is None:
                self.warnings.append(
                    f"Dependency references unknown variable {operand.value!r} — skipped"
                )
                return []
            return [node_id]
        if isinstance(operand, cst.Call):
            base_name, _ = _call_chain_base(operand)
            if base_name is not None and base_name in self.func_to_node:
                return [self.func_to_node[base_name]]
            self.warnings.append("Dependency references an unknown callable — skipped")
            return []
        if isinstance(operand, (cst.List, cst.Tuple)):
            ids: list[str] = []
            for element in operand.elements:
                if isinstance(element, cst.Element):
                    ids.extend(self._resolve_operand(element.value))
            return ids
        self.warnings.append("Unsupported dependency operand — skipped")
        return []

    def _label_value(self, operand: cst.BaseExpression) -> str | None:
        """`Label("x")` operand in a dependency chain -> "x"."""
        if (
            isinstance(operand, cst.Call)
            and isinstance(operand.func, cst.Name)
            and operand.func.value == "Label"
            and operand.args
        ):
            ok, value = _literal(self.module, operand.args[0].value)
            if ok and isinstance(value, str):
                return value
        return None

    def _visit_expr(self, path: Path, expr: cst.BaseExpression) -> None:
        terms = _chain_terms(expr)
        if terms is not None:
            self.dep_paths.append(path)
            previous: list[str] = []
            pending_label: str | None = None
            for op, operand in terms:
                label = self._label_value(operand)
                if label is not None:
                    pending_label = label
                    continue  # `a >> Label("x") >> b`: label applies to the next hop
                current = self._resolve_operand(operand)
                if op == ">>":
                    for src in previous:
                        for dst in current:
                            self.edges.append(
                                Edge(source=src, target=dst, label=pending_label)
                            )
                elif op == "<<":
                    for dst in previous:
                        for src in current:
                            self.edges.append(
                                Edge(source=src, target=dst, label=pending_label)
                            )
                pending_label = None
                previous = current
            return
        if isinstance(expr, cst.Call) and isinstance(expr.func, cst.Name):
            name = expr.func.value
            if name == "chain":
                self.dep_paths.append(path)
                groups = [self._resolve_operand(arg.value) for arg in expr.args]
                for left, right in zip(groups, groups[1:], strict=False):
                    for src in left:
                        for dst in right:
                            self.edges.append(Edge(source=src, target=dst))
                return
        if isinstance(expr, cst.Call):
            base_name, _ = _call_chain_base(expr)
            if base_name is not None and base_name in self.func_to_node:
                # bare `my_taskflow_func()` / `f.expand(...)` statement
                binding = self.bindings[self.func_to_node[base_name]]
                binding.call_path = path
                binding.inline_call_only = False


def parse_source(source: str) -> ParsedDag:
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        raise ParseError(f"Syntax error: {exc.message}") from exc

    containers = _find_containers(module)
    if not containers:
        raise ParseError(
            "No DAG found (supported: a @dag-decorated function or a top-level `with DAG(...):`)"
        )
    warnings: list[str] = []
    if len(containers) > 1:
        warnings.append(
            f"File defines {len(containers)} DAGs — editing the first one only"
        )
    style, container_index, container = containers[0]

    if style == "decorator":
        assert isinstance(container, cst.FunctionDef)
        decorator = _decorator_named(container, "dag")
        call = (
            decorator.decorator
            if decorator is not None and isinstance(decorator.decorator, cst.Call)
            else None
        )
        meta, default_args_extras = _meta_from_call(
            module, call, container.name.value, warnings
        )
        body = container.body
    else:
        assert isinstance(container, cst.With)
        dag_call = next(
            item.item
            for item in container.items
            if isinstance(item.item, cst.Call)
            and isinstance(item.item.func, cst.Name)
            and item.item.func.value == "DAG"
        )
        meta, default_args_extras = _meta_from_call(module, dag_call, None, warnings)
        body = container.body

    if not isinstance(body, cst.IndentedBlock):
        raise ParseError("Unsupported DAG body layout")

    builder = _GraphBuilder(module)
    builder.walk(body, (), None)
    warnings.extend(builder.warnings)

    # De-duplicate edges, keep order.
    seen: set[tuple[str, str]] = set()
    edges: list[Edge] = []
    for edge in builder.edges:
        key = (edge.source, edge.target)
        if key not in seen and edge.source != edge.target:
            seen.add(key)
            edges.append(edge)

    graph = GraphModel(
        dag=meta,
        nodes=[builder.bindings[node_id].node for node_id in builder.order],
        edges=edges,
        groups=builder.groups,
    )
    return ParsedDag(
        module=module,
        graph=graph,
        warnings=warnings,
        style=style,
        container_index=container_index,
        bindings=builder.bindings,
        dep_paths=builder.dep_paths,
        var_to_node=builder.var_to_node,
        group_paths=builder.group_paths,
        group_vars=builder.group_vars,
        default_args_extras=default_args_extras,
    )


def parse_graph(source: str) -> tuple[GraphModel, list[str]]:
    parsed = parse_source(source)
    return parsed.graph, parsed.warnings
