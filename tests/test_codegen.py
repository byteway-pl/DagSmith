from __future__ import annotations

import ast

import pytest

from dagsmith.core.codegen import generate_source
from dagsmith.core.model import DagMeta, Edge, GraphModel, GraphValidationError, TaskNode


def _etl_graph() -> GraphModel:
    return GraphModel(
        dag=DagMeta(dag_id="my_etl", schedule="@daily", tags=["dagsmith"]),
        nodes=[
            TaskNode(id="start", block_id="empty"),
            TaskNode(id="extract", block_id="bash", params={"bash_command": "echo x"}),
            TaskNode(id="transform", block_id="python", params={"body": "return 42"}),
            TaskNode(id="load", block_id="bash", params={"bash_command": "echo done"}),
        ],
        edges=[
            Edge(source="start", target="extract"),
            Edge(source="extract", target="transform"),
            Edge(source="transform", target="load"),
        ],
    )


def test_generates_parseable_python_with_expected_structure() -> None:
    source = generate_source(_etl_graph())
    ast.parse(source)  # must be valid Python
    assert source.startswith("# dagsmith: v1")
    assert '@dag(schedule=\'@daily\', tags=[\'dagsmith\'])' in source
    assert "def my_etl():" in source
    assert 't_extract = BashOperator(task_id="extract", bash_command=\'echo x\')' in source
    assert "@task" in source
    assert "def transform():" in source
    assert "return 42" in source
    assert "t_start >> t_extract" in source
    assert source.rstrip().endswith("my_etl()")


def test_codegen_is_deterministic() -> None:
    assert generate_source(_etl_graph()) == generate_source(_etl_graph())


def test_topological_definition_order() -> None:
    source = generate_source(_etl_graph())
    assert source.index("t_start") < source.index("t_extract") < source.index("def transform")


def test_empty_graph_generates_pass_body() -> None:
    source = generate_source(GraphModel(dag=DagMeta(dag_id="empty_dag")))
    ast.parse(source)
    assert "    pass" in source
    assert "schedule=None" in source


def test_cycle_is_rejected() -> None:
    graph = GraphModel(
        dag=DagMeta(dag_id="cyclic"),
        nodes=[TaskNode(id="a", block_id="empty"), TaskNode(id="b", block_id="empty")],
        edges=[Edge(source="a", target="b"), Edge(source="b", target="a")],
    )
    with pytest.raises(GraphValidationError, match="cycle"):
        generate_source(graph)


def test_duplicate_task_id_rejected() -> None:
    graph = GraphModel(
        dag=DagMeta(dag_id="dup"),
        nodes=[TaskNode(id="a", block_id="empty"), TaskNode(id="a", block_id="empty")],
    )
    with pytest.raises(GraphValidationError, match="Duplicate"):
        generate_source(graph)


def test_missing_required_param_rejected() -> None:
    graph = GraphModel(
        dag=DagMeta(dag_id="d"),
        nodes=[TaskNode(id="t", block_id="trigger_dag")],
    )
    with pytest.raises(GraphValidationError, match="trigger_dag_id"):
        generate_source(graph)


def test_invalid_identifiers_rejected_by_model() -> None:
    with pytest.raises(ValueError):
        TaskNode(id="not valid", block_id="empty")
    with pytest.raises(ValueError):
        DagMeta(dag_id="123bad")
    # Airflow-style ids with dots/dashes are allowed
    assert TaskNode(id="my-task.v2", block_id="empty").id == "my-task.v2"


def test_int_param_and_multiline_body() -> None:
    graph = GraphModel(
        dag=DagMeta(dag_id="m"),
        nodes=[
            TaskNode(
                id="calc",
                block_id="python",
                params={"body": "x = 1\nreturn x + 1", "retries": 3},
            )
        ],
    )
    source = generate_source(graph)
    ast.parse(source)
    assert "@task(retries=3)" in source
    assert "        x = 1" in source
    assert "        return x + 1" in source


def test_codegen_endpoint_and_catalog(api_client) -> None:
    graph = _etl_graph().model_dump()
    response = api_client.post("/api/v1/codegen", json={"graph": graph})
    assert response.status_code == 200
    assert "def my_etl():" in response.json()["source"]

    bad = dict(graph, edges=[{"source": "start", "target": "nope"}])
    response = api_client.post("/api/v1/codegen", json={"graph": bad})
    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"

    blocks = api_client.get("/api/v1/operators")
    assert blocks.status_code == 200
    ids = [b["block_id"] for b in blocks.json()]
    assert {"empty", "bash", "python", "trigger_dag"} <= set(ids)
