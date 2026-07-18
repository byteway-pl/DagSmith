"""Block palette: curated built-in blocks + blocks introspected from providers.

Built-in blocks (bash/python/empty/trigger_dag) are hand-tuned and always
available. Provider blocks (M5) are discovered from installed provider
packages: provider metadata lists operator/sensor modules, whose
BaseOperator subclasses get a parameter schema introspected from their
``__init__`` signature. Discovery is expensive, so results are cached
process-wide with a TTL; everything degrades gracefully to the built-ins
when Airflow is not importable (unit tests, CLI).
"""

from __future__ import annotations

import inspect
import logging
import time
import types
import typing
from importlib import import_module
from typing import Literal

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

ParamType = Literal["str", "text", "python", "int", "bool", "dict"]

# Parameter names that deserve a multiline editor.
_TEXT_PARAM_NAMES = {"bash_command", "sql", "command", "query", "script", "hql", "code"}
_MAX_PARAMS_PER_BLOCK = 25


class BlockParam(BaseModel):
    name: str
    label: str
    type: ParamType
    required: bool = False
    default: str | int | bool | None = None
    help: str | None = None


class BlockDef(BaseModel):
    block_id: str
    label: str
    category: str
    description: str
    # Import line required by the generated code; None for taskflow (@task).
    import_stmt: str | None = None
    # Operator class name as used in code; None for taskflow (@task).
    class_name: str | None = None
    params: list[BlockParam] = Field(default_factory=list)


BUILTIN_BLOCKS: list[BlockDef] = [
    BlockDef(
        block_id="empty",
        label="Empty",
        category="Core",
        description="Marker task that does nothing (EmptyOperator).",
        import_stmt="from airflow.providers.standard.operators.empty import EmptyOperator",
        class_name="EmptyOperator",
    ),
    BlockDef(
        block_id="bash",
        label="Bash",
        category="Core",
        description="Run a bash command (BashOperator).",
        import_stmt="from airflow.providers.standard.operators.bash import BashOperator",
        class_name="BashOperator",
        params=[
            BlockParam(
                name="bash_command",
                label="Bash command",
                type="text",
                required=True,
                default="echo hello",
            ),
            BlockParam(name="retries", label="Retries", type="int"),
        ],
    ),
    BlockDef(
        block_id="python",
        label="Python",
        category="Core",
        description="Run Python code as a @task-decorated function.",
        params=[
            BlockParam(
                name="body",
                label="Function body",
                type="python",
                required=True,
                default="pass",
                help="Body of the @task function (without the def line).",
            ),
            BlockParam(name="retries", label="Retries", type="int"),
        ],
    ),
    BlockDef(
        block_id="trigger_dag",
        label="Trigger DAG",
        category="Core",
        description="Trigger another DAG (TriggerDagRunOperator).",
        import_stmt=(
            "from airflow.providers.standard.operators.trigger_dagrun "
            "import TriggerDagRunOperator"
        ),
        class_name="TriggerDagRunOperator",
        params=[
            BlockParam(
                name="trigger_dag_id",
                label="DAG id to trigger",
                type="str",
                required=True,
            ),
        ],
    ),
]

def _trigger_rule_param() -> BlockParam:
    return BlockParam(
        name="trigger_rule",
        label="Trigger rule",
        type="str",
        help="When the task runs relative to upstream states (default: all_success)",
    )


# Every block accepts BaseOperator's trigger_rule.
for _block in BUILTIN_BLOCKS:
    _block.params.append(_trigger_rule_param())

_BUILTIN_BY_ID = {block.block_id: block for block in BUILTIN_BLOCKS}
_BUILTIN_CLASS_NAMES = {b.class_name for b in BUILTIN_BLOCKS if b.class_name}


# -- provider introspection -------------------------------------------------


def _annotation_to_type(annotation: object) -> ParamType:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _annotation_to_type(args[0])
        # Mixed unions like `str | list[str]` (typical for sql): prefer the
        # simplest editable member — a plain string is always accepted.
        member_types = {_annotation_to_type(a) for a in args}
        for preferred in ("str", "int", "bool", "dict"):
            if preferred in member_types:
                return preferred  # type: ignore[return-value]
        return "python"
    if annotation is str:
        return "str"
    if annotation is int:
        return "int"
    if annotation is bool:
        return "bool"
    if annotation is dict or origin is dict:
        return "dict"
    if isinstance(annotation, str):
        # string annotations (from __future__ annotations)
        text = annotation.replace(" ", "")
        parts = [p.removeprefix("Optional[").removesuffix("]") for p in text.split("|")]
        parts = [p for p in parts if p != "None"]
        if "str" in parts:
            return "str"
        if "int" in parts:
            return "int"
        if "bool" in parts:
            return "bool"
        if any(
            p.startswith(("dict", "Dict", "Mapping", "MutableMapping")) for p in parts
        ):
            return "dict"
    return "python"


def _is_base_operator_class(klass: type) -> bool:
    """The generic operator base — its ~40 kwargs would flood every form."""
    return klass.__name__ == "BaseOperator" or klass.__module__.startswith(
        ("airflow.sdk.bases", "airflow.models.baseoperator")
    )


def _params_from_signature(cls: type) -> list[BlockParam]:
    """Introspect ``__init__`` across the MRO.

    Many operators (e.g. the SQL family) accept their real parameters via a
    parent class and just forward ``**kwargs`` — TeradataOperator's ``sql``
    lives on SQLExecuteQueryOperator. We walk parents for as long as the child
    forwards ``**kwargs``, stopping before BaseOperator.
    """
    params: list[BlockParam] = []
    seen: set[str] = set()
    for klass in cls.__mro__:
        if klass is object or _is_base_operator_class(klass):
            break
        if "__init__" not in vars(klass):
            continue  # class doesn't define its own __init__ — look further up
        try:
            signature = inspect.signature(klass.__init__)
        except (TypeError, ValueError):
            break
        has_var_kwargs = False
        for name, parameter in signature.parameters.items():
            if parameter.kind == parameter.VAR_KEYWORD:
                has_var_kwargs = True
            if name in ("self", "args", "kwargs") or name.startswith("_"):
                continue
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                continue
            if name in seen:
                continue
            seen.add(name)
            param_type = _annotation_to_type(parameter.annotation)
            if param_type == "str" and name in _TEXT_PARAM_NAMES:
                param_type = "text"
            required = parameter.default is inspect.Parameter.empty
            default: str | int | bool | None = None
            if not required and isinstance(parameter.default, (str, int, bool)):
                default = parameter.default
            params.append(
                BlockParam(
                    name=name,
                    label=name.replace("_", " ").capitalize(),
                    type=param_type,
                    required=required,
                    default=default,
                )
            )
            if len(params) >= _MAX_PARAMS_PER_BLOCK:
                return params
        if not has_var_kwargs:
            break  # parents can't receive extra kwargs through this class
    return params


def _short_provider_name(package: str) -> str:
    return package.removeprefix("apache-airflow-providers-").replace("-", " ")


def _blocks_from_module(module_name: str, category: str) -> list[BlockDef]:
    from airflow.models import BaseOperator

    blocks: list[BlockDef] = []
    module = import_module(module_name)
    for name, obj in vars(module).items():
        if (
            not inspect.isclass(obj)
            or obj.__module__ != module_name
            or not issubclass(obj, BaseOperator)
            or name.startswith("_")
            or inspect.isabstract(obj)
            or name in _BUILTIN_CLASS_NAMES
        ):
            continue
        doc = inspect.getdoc(obj) or ""
        params = _params_from_signature(obj)
        if all(p.name != "trigger_rule" for p in params):
            params.append(_trigger_rule_param())
        blocks.append(
            BlockDef(
                block_id=f"{module_name}.{name}",
                label=name,
                category=category,
                description=doc.split("\n\n")[0][:300] if doc else name,
                import_stmt=f"from {module_name} import {name}",
                class_name=name,
                params=params,
            )
        )
    return blocks


def _load_provider_blocks() -> list[BlockDef]:
    from airflow.providers_manager import ProvidersManager

    blocks: list[BlockDef] = []
    seen_classes: set[str] = set(_BUILTIN_CLASS_NAMES)
    manager = ProvidersManager()
    for package_name, provider in manager.providers.items():
        info = provider.data
        category = _short_provider_name(package_name)
        for section in ("operators", "sensors"):
            for integration in info.get(section, []) or []:
                for module_name in integration.get("python-modules", []) or []:
                    try:
                        for block in _blocks_from_module(module_name, category):
                            if block.class_name in seen_classes:
                                continue
                            seen_classes.add(block.class_name or "")
                            blocks.append(block)
                    except Exception as exc:
                        log.debug("Skipping module %s: %s", module_name, exc)
    blocks.sort(key=lambda b: (b.category, b.label))
    return blocks


_provider_cache: list[BlockDef] | None = None
_provider_cache_at: float = 0.0


def provider_blocks() -> list[BlockDef]:
    """Cached provider discovery; empty when Airflow is unavailable."""
    global _provider_cache, _provider_cache_at
    from dagsmith.config import get_int

    try:
        ttl = get_int("catalog_ttl")
    except Exception:
        ttl = 600
    now = time.monotonic()
    if _provider_cache is not None and now - _provider_cache_at < ttl:
        return _provider_cache
    try:
        _provider_cache = _load_provider_blocks()
    except Exception as exc:
        log.info("Provider block discovery unavailable: %s", exc)
        _provider_cache = []
    _provider_cache_at = now
    return _provider_cache


# -- public API --------------------------------------------------------------


def list_blocks() -> list[BlockDef]:
    return [*BUILTIN_BLOCKS, *provider_blocks()]


def catalog_fingerprint() -> str:
    """Hash of the full block schema (ids + params) — drives the /operators ETag."""
    import hashlib

    digest = hashlib.sha256()
    for block in list_blocks():
        digest.update(block.model_dump_json().encode())
    return digest.hexdigest()[:16]


def get_block(block_id: str) -> BlockDef:
    if block_id in _BUILTIN_BY_ID:
        return _BUILTIN_BY_ID[block_id]
    for block in provider_blocks():
        if block.block_id == block_id:
            return block
    raise KeyError(f"Unknown block: {block_id}")


def block_by_class_name(class_name: str) -> BlockDef | None:
    """Resolve an operator class name (as written in DAG code) to a block."""
    for block in BUILTIN_BLOCKS:
        if block.class_name == class_name:
            return block
    for block in provider_blocks():
        if block.class_name == class_name:
            return block
    return None
