"""TaskGroup as a dependency endpoint: parse, from-scratch, transform."""

from __future__ import annotations

import ast
from pathlib import Path

from dagsmith.core.codegen import generate_source
from dagsmith.core.model import DagMeta, Edge, GraphModel, TaskGroupNode, TaskNode
from dagsmith.core.parser import parse_graph

CORPUS = Path(__file__).parent / "corpus"


def test_parse_group_endpoint() -> None:
    graph, warnings = parse_graph((CORPUS / "t3_group_deps.py").read_text())
    edges = {(e.source, e.target) for e in graph.edges}
    # `start >> etl >> end` — etl is a group endpoint
    assert edges == {("start", "etl"), ("etl", "end")}
    assert {g.id for g in graph.groups} == {"etl"}
    assert warnings == []


def test_group_edges_roundtrip_invariant() -> None:
    source = (CORPUS / "t3_group_deps.py").read_text()
    graph, _ = parse_graph(source)
    assert generate_source(graph, base_source=source) == source


def test_from_scratch_with_group_edges() -> None:
    graph = GraphModel(
        dag=DagMeta(dag_id="built"),
        nodes=[
            TaskNode(id="start", block_id="empty"),
            TaskNode(id="a", block_id="empty", group_id="etl"),
            TaskNode(id="b", block_id="empty", group_id="etl"),
            TaskNode(id="end", block_id="empty"),
        ],
        edges=[Edge(source="start", target="etl"), Edge(source="etl", target="end")],
        groups=[TaskGroupNode(id="etl", label="etl", parent_id=None)],
    )
    source = generate_source(graph)
    ast.parse(source)
    assert "with TaskGroup('etl') as g_etl:" in source
    assert "from airflow.sdk import TaskGroup" in source
    assert "t_start >> g_etl" in source
    assert "g_etl >> t_end" in source
    # round-trips back to the same graph
    reparsed, _ = parse_graph(source)
    assert {(e.source, e.target) for e in reparsed.edges} == {
        ("start", "etl"),
        ("etl", "end"),
    }
    assert next(n for n in reparsed.nodes if n.id == "a").group_id == "etl"


def test_add_group_edge_reuses_existing_asname() -> None:
    # `etl` already has `as etl` in the corpus — reuse it, don't add a new one.
    source = (CORPUS / "t3_loops_and_groups.py").read_text()
    graph, _ = parse_graph(source)
    graph.edges.append(Edge(source="start", target="etl"))
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "start >> etl" in result
    assert "g_etl" not in result  # existing var reused
    reparsed, _ = parse_graph(result)
    assert ("start", "etl") in {(e.source, e.target) for e in reparsed.edges}


def test_add_group_edge_to_nested_group_adds_asname() -> None:
    # `etl.transforms` has no `as` in the corpus — transform must add one.
    source = (CORPUS / "t3_loops_and_groups.py").read_text()
    graph, _ = parse_graph(source)
    graph.edges.append(Edge(source="start", target="etl.transforms"))
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert 'with TaskGroup("transforms") as g_etl_transforms:' in result
    assert "start >> g_etl_transforms" in result
    reparsed, _ = parse_graph(result)
    assert ("start", "etl.transforms") in {(e.source, e.target) for e in reparsed.edges}
    # existing intra-group structure survives
    assert next(n for n in reparsed.nodes if n.id == "t1").group_id == "etl.transforms"


def test_group_to_group_edge() -> None:
    graph = GraphModel(
        dag=DagMeta(dag_id="g2g"),
        nodes=[
            TaskNode(id="a", block_id="empty", group_id="left"),
            TaskNode(id="b", block_id="empty", group_id="right"),
        ],
        edges=[Edge(source="left", target="right")],
        groups=[
            TaskGroupNode(id="left", label="left", parent_id=None),
            TaskGroupNode(id="right", label="right", parent_id=None),
        ],
    )
    source = generate_source(graph)
    ast.parse(source)
    assert "g_left >> g_right" in source
    reparsed, _ = parse_graph(source)
    assert ("left", "right") in {(e.source, e.target) for e in reparsed.edges}
