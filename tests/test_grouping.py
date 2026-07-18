"""Visual task-grouping via the transforming codegen."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dagsmith.core.codegen import generate_source
from dagsmith.core.model import GraphValidationError, TaskGroupNode, TaskNode
from dagsmith.core.parser import parse_graph

CORPUS = Path(__file__).parent / "corpus"


def _load(name: str):
    source = (CORPUS / name).read_text()
    graph, _ = parse_graph(source)
    return source, graph


def test_create_group_and_move_tasks_in() -> None:
    source, graph = _load("t2_dag_decorator.py")
    graph.groups.append(TaskGroupNode(id="etl", label="etl", parent_id=None))
    for node in graph.nodes:
        if node.id in ("extract", "load"):
            node.group_id = "etl"
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "with TaskGroup('etl'):" in result
    assert "from airflow.sdk import TaskGroup" in result  # import added
    assert "# entry point marker" in result  # untouched comment survives

    reparsed, _ = parse_graph(result)
    by_id = {n.id: n for n in reparsed.nodes}
    assert by_id["extract"].group_id == "etl"
    assert by_id["load"].group_id == "etl"
    assert by_id["start"].group_id is None
    # edges survive the canonical dep rewrite
    assert {(e.source, e.target) for e in reparsed.edges} == {
        ("start", "extract"),
        ("extract", "transform"),
        ("transform", "load"),
    }


def test_move_task_out_of_nested_group() -> None:
    source, graph = _load("t3_loops_and_groups.py")
    for node in graph.nodes:
        if node.id == "t2":
            node.group_id = None
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    reparsed, _ = parse_graph(result)
    by_id = {n.id: n for n in reparsed.nodes}
    assert by_id["t2"].group_id is None
    assert by_id["t1"].group_id == "etl.transforms"
    # statement relocated verbatim
    assert 'BashOperator(task_id="t2", bash_command="echo t2")' in result


def test_move_task_between_existing_groups() -> None:
    source, graph = _load("t3_loops_and_groups.py")
    for node in graph.nodes:
        if node.id == "extract":
            node.group_id = "etl.transforms"
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    reparsed, _ = parse_graph(result)
    assert next(n for n in reparsed.nodes if n.id == "extract").group_id == "etl.transforms"


def test_add_new_task_directly_into_existing_group() -> None:
    source, graph = _load("t3_loops_and_groups.py")
    graph.nodes.append(
        TaskNode(
            id="cleanup",
            block_id="bash",
            params={"bash_command": "echo cleanup"},
            group_id="etl",
        )
    )
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    reparsed, _ = parse_graph(result)
    assert next(n for n in reparsed.nodes if n.id == "cleanup").group_id == "etl"


def test_move_taskflow_node_into_group_moves_def_and_call() -> None:
    source, graph = _load("t2_dag_decorator.py")
    graph.groups.append(TaskGroupNode(id="tg", label="tg", parent_id=None))
    for node in graph.nodes:
        if node.id == "transform":
            node.group_id = "tg"
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    reparsed, _ = parse_graph(result)
    transform = next(n for n in reparsed.nodes if n.id == "transform")
    assert transform.group_id == "tg"
    assert transform.block_id == "python"
    # deps still intact after canonicalization
    assert {(e.source, e.target) for e in reparsed.edges} == {
        ("start", "extract"),
        ("extract", "transform"),
        ("transform", "load"),
    }


def test_nested_new_group_under_new_group_rejected() -> None:
    source, graph = _load("t2_dag_decorator.py")
    graph.groups.append(TaskGroupNode(id="a", label="a", parent_id=None))
    graph.groups.append(TaskGroupNode(id="a.b", label="b", parent_id="a"))
    with pytest.raises(GraphValidationError, match="nesting under another new group"):
        generate_source(graph, base_source=source)


def test_grouping_preserves_import_when_already_present() -> None:
    source, graph = _load("t3_loops_and_groups.py")
    graph.groups.append(TaskGroupNode(id="reports", label="reports", parent_id=None))
    for node in graph.nodes:
        if node.id == "start":
            node.group_id = "reports"
    result = generate_source(graph, base_source=source)
    assert result.count("import TaskGroup") == 1
