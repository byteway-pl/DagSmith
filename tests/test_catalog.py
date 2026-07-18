"""Provider catalog introspection and dynamic (provider) blocks end-to-end."""

from __future__ import annotations

import ast
import time

import pytest

from dagsmith.core import catalog
from dagsmith.core.catalog import BlockDef, BlockParam, _annotation_to_type
from dagsmith.core.codegen import generate_source
from dagsmith.core.model import DagMeta, GraphModel, GraphValidationError, TaskNode
from dagsmith.core.parser import parse_graph


class _FakeOperator:
    def __init__(
        self,
        target_table: str,
        rows: int = 100,
        overwrite: bool = False,
        on_error=None,
        sql: str = "SELECT 1",
        _private: str = "x",
        **kwargs,
    ) -> None: ...


def test_annotation_mapping() -> None:
    assert _annotation_to_type(str) == "str"
    assert _annotation_to_type(int) == "int"
    assert _annotation_to_type(bool) == "bool"
    assert _annotation_to_type(str | None) == "str"
    assert _annotation_to_type("str | None") == "str"
    assert _annotation_to_type(dict) == "dict"
    assert _annotation_to_type(dict[str, str]) == "dict"
    assert _annotation_to_type("dict[str, str] | None") == "dict"
    assert _annotation_to_type("Mapping[str, Any]") == "dict"
    assert _annotation_to_type(None) == "python"
    # mixed unions prefer the simplest editable member (typical: sql of the SQL family)
    assert _annotation_to_type(str | list) == "str"
    assert _annotation_to_type("str | list[str]") == "str"
    assert _annotation_to_type("list[str] | str | None") == "str"


def test_params_from_signature() -> None:
    params = {p.name: p for p in catalog._params_from_signature(_FakeOperator)}
    assert "_private" not in params
    assert "kwargs" not in params
    assert params["target_table"].required is True
    assert params["target_table"].type == "str"
    assert params["rows"].type == "int"
    assert params["rows"].default == 100
    assert params["overwrite"].type == "bool"
    assert params["on_error"].type == "python"
    assert params["sql"].type == "text"  # multiline heuristic


class BaseOperator:  # noqa: N801 — name triggers the MRO stop condition
    def __init__(self, task_id=None, retries: int = 0, **kwargs) -> None: ...


class _ParentSqlOperator(BaseOperator):
    def __init__(self, *, sql: str | list[str], autocommit: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)


class _ChildOperator(_ParentSqlOperator):
    def __init__(self, *, conn_id: str = "default", **kwargs) -> None:
        super().__init__(**kwargs)


def test_params_walk_the_mro_for_kwargs_forwarding() -> None:
    """TeradataOperator pattern: `sql` lives on the parent, child forwards **kwargs."""
    params = {p.name: p for p in catalog._params_from_signature(_ChildOperator)}
    assert params["conn_id"].type == "str"
    assert "sql" in params, "parent params must be discovered through **kwargs"
    assert params["sql"].required is True
    assert params["sql"].type == "text"  # str|list[str] -> str -> text heuristic
    assert params["autocommit"].type == "bool"
    # generic BaseOperator kwargs are NOT pulled in
    assert "task_id" not in params
    assert "retries" not in params


def test_provider_blocks_empty_without_airflow() -> None:
    catalog._provider_cache = None
    assert catalog.provider_blocks() == []
    # builtins always present
    assert {b.block_id for b in catalog.list_blocks()} >= {"empty", "bash", "python"}


@pytest.fixture
def fake_provider_block():
    block = BlockDef(
        block_id="fake.provider.module.SqlOperator",
        label="SqlOperator",
        category="fake provider",
        description="Fake SQL operator",
        import_stmt="from fake.provider.module import SqlOperator",
        class_name="SqlOperator",
        params=[
            BlockParam(name="sql", label="Sql", type="text", required=True),
            BlockParam(name="hook_params", label="Hook params", type="python"),
        ],
    )
    catalog._provider_cache = [block]
    catalog._provider_cache_at = time.monotonic()
    yield block
    catalog._provider_cache = None


def test_provider_block_codegen_and_roundtrip(fake_provider_block: BlockDef) -> None:
    graph = GraphModel(
        dag=DagMeta(dag_id="uses_provider"),
        nodes=[
            TaskNode(
                id="load_sql",
                block_id=fake_provider_block.block_id,
                params={"sql": "SELECT * FROM t", "hook_params": "{'retries': 2}"},
            )
        ],
    )
    source = generate_source(graph)
    ast.parse(source)
    assert "from fake.provider.module import SqlOperator" in source
    assert "hook_params={'retries': 2}" in source  # raw python expression, not quoted

    # parse back: class resolved through the catalog
    reparsed, _ = parse_graph(source)
    node = reparsed.nodes[0]
    assert node.block_id == fake_provider_block.block_id
    assert node.opaque is False
    assert node.params["sql"] == "SELECT * FROM t"
    assert node.params["hook_params"] == "{'retries': 2}"

    # invariant + one-line param edit via transform
    assert generate_source(reparsed, base_source=source) == source
    node.params["sql"] = "SELECT 42"
    edited = generate_source(reparsed, base_source=source)
    assert "SELECT 42" in edited
    assert "hook_params={'retries': 2}" in edited


def test_invalid_python_expression_param_rejected(fake_provider_block: BlockDef) -> None:
    graph = GraphModel(
        dag=DagMeta(dag_id="bad_expr"),
        nodes=[
            TaskNode(
                id="x",
                block_id=fake_provider_block.block_id,
                params={"sql": "SELECT 1", "hook_params": "not a ( valid expr"},
            )
        ],
    )
    with pytest.raises(GraphValidationError, match="valid Python expression"):
        generate_source(graph)


def test_connections_endpoint(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    # no `connection` table in the unit-test DB -> degrade to env-derived list
    monkeypatch.setenv("AIRFLOW_CONN_TERADATA_PROD", "teradata://host:1025/db")
    monkeypatch.setenv("AIRFLOW_CONN_MY_API", "http://api.example.com")
    response = api_client.get("/api/v1/connections")
    assert response.status_code == 200
    by_id = {c["conn_id"]: c["conn_type"] for c in response.json()}
    assert by_id["teradata_prod"] == "teradata"
    assert by_id["my_api"] == "http"


def test_operators_endpoint_etag(api_client) -> None:
    first = api_client.get("/api/v1/operators")
    assert first.status_code == 200
    etag = first.headers["etag"]
    cached = api_client.get("/api/v1/operators", headers={"If-None-Match": etag})
    assert cached.status_code == 304
