"""Group removal / rename (remove+add) via the transforming codegen."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dagsmith.core.codegen import generate_source
from dagsmith.core.model import GraphValidationError, TaskGroupNode
from dagsmith.core.parser import parse_graph

CORPUS = Path(__file__).parent / "corpus"


def _load(name: str):
    source = (CORPUS / name).read_text()
    graph, _ = parse_graph(source)
    return source, graph


def test_remove_nested_group_moves_tasks_to_parent() -> None:
    source, graph = _load("t3_loops_and_groups.py")
    graph.groups = [g for g in graph.groups if g.id != "etl.transforms"]
    for node in graph.nodes:
        if node.group_id == "etl.transforms":
            node.group_id = "etl"
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert 'TaskGroup("transforms")' not in result
    reparsed, _ = parse_graph(result)
    by_id = {n.id: n for n in reparsed.nodes}
    assert by_id["t1"].group_id == "etl"
    assert by_id["t2"].group_id == "etl"
    assert {g.id for g in reparsed.groups} == {"etl"}
    # tasks and their params survive the relocation verbatim
    assert 'BashOperator(task_id="t1", bash_command="echo t1")' in result


def test_remove_group_cascade_to_top_level() -> None:
    source, graph = _load("t3_loops_and_groups.py")
    graph.groups = []
    for node in graph.nodes:
        node.group_id = None
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "TaskGroup(" not in result
    reparsed, _ = parse_graph(result)
    assert reparsed.groups == []
    assert all(n.group_id is None for n in reparsed.nodes)
    assert {n.id for n in reparsed.nodes} >= {"start", "extract", "t1", "t2"}
    assert {(e.source, e.target) for e in reparsed.edges} == {
        ("extract", "t1"),
        ("extract", "t2"),
        ("start", "extract"),
    }


def test_rename_group_via_remove_add() -> None:
    source, graph = _load("t3_loops_and_groups.py")
    # rename leaf group etl.transforms -> etl.stage (parent exists in base)
    renamed = TaskGroupNode(id="etl.stage", label="stage", parent_id="etl")
    graph.groups = [g if g.id != "etl.transforms" else renamed for g in graph.groups]
    for node in graph.nodes:
        if node.group_id == "etl.transforms":
            node.group_id = "etl.stage"
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "TaskGroup('stage')" in result
    assert 'TaskGroup("transforms")' not in result
    reparsed, _ = parse_graph(result)
    assert {g.id for g in reparsed.groups} == {"etl", "etl.stage"}
    assert next(n for n in reparsed.nodes if n.id == "t1").group_id == "etl.stage"


def test_remove_group_with_code_only_block_rejected() -> None:
    source = """\
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, TaskGroup


@dag(schedule=None)
def guarded():
    with TaskGroup("tg"):
        a = BashOperator(task_id="a", bash_command="echo a")
        for i in range(2):
            BashOperator(task_id=f"x_{i}", bash_command="echo x")


guarded()
"""
    graph, _ = parse_graph(source)
    graph.groups = []
    for node in graph.nodes:
        node.group_id = None
    with pytest.raises(GraphValidationError, match="code-only"):
        generate_source(graph, base_source=source)
