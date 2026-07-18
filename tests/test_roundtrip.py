"""Parser + transforming codegen: the round-trip invariant and mutation tests.

Invariant: ``generate_source(parse(src), base_source=src) == src`` byte-for-byte
for every corpus file when the graph is unchanged.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dagsmith.core.codegen import generate_source
from dagsmith.core.model import DagMeta, Edge, GraphModel, TaskNode
from dagsmith.core.parser import ParseError, parse_graph

CORPUS = sorted((Path(__file__).parent / "corpus").glob("*.py"))


def _generated_corpus_source() -> str:
    """A T1 file: output of the from-scratch generator."""
    graph = GraphModel(
        dag=DagMeta(dag_id="t1_generated", schedule="@daily", tags=["dagsmith"]),
        nodes=[
            TaskNode(id="start", block_id="empty"),
            TaskNode(id="work", block_id="python", params={"body": "return 1", "retries": 2}),
            TaskNode(id="done", block_id="bash", params={"bash_command": "echo done"}),
        ],
        edges=[Edge(source="start", target="work"), Edge(source="work", target="done")],
    )
    return generate_source(graph)


def _all_sources() -> list[tuple[str, str]]:
    sources = [(path.name, path.read_text()) for path in CORPUS]
    sources.append(("t1_generated(virtual)", _generated_corpus_source()))
    return sources


@pytest.mark.parametrize(
    "name,source",
    _all_sources(),
    ids=lambda v: v if isinstance(v, str) and len(v) < 40 else "",
)
def test_roundtrip_invariant(name: str, source: str) -> None:
    graph, _warnings = parse_graph(source)
    assert generate_source(graph, base_source=source) == source


def test_parse_dag_decorator_style() -> None:
    source = (Path(__file__).parent / "corpus" / "t2_dag_decorator.py").read_text()
    graph, warnings = parse_graph(source)
    assert graph.dag.dag_id == "example_etl"
    assert graph.dag.tags == ["dagsmith-dev"]
    assert [n.id for n in graph.nodes] == ["start", "extract", "transform", "load"]
    transform = next(n for n in graph.nodes if n.id == "transform")
    assert transform.block_id == "python"
    assert 'return "transformed"' in str(transform.params["body"])
    assert {(e.source, e.target) for e in graph.edges} == {
        ("start", "extract"),
        ("extract", "transform"),
        ("transform", "load"),
    }
    assert warnings == []


def test_parse_with_dag_style_lists_and_left_shift() -> None:
    source = (Path(__file__).parent / "corpus" / "t2_with_dag.py").read_text()
    graph, _ = parse_graph(source)
    assert graph.dag.dag_id == "legacy_style"
    assert graph.dag.schedule == "@hourly"
    fan_b = next(n for n in graph.nodes if n.id == "fan_b")
    assert fan_b.params == {"bash_command": "echo b", "retries": 1}
    assert {(e.source, e.target) for e in graph.edges} == {
        ("begin", "fan_a"),
        ("begin", "fan_b"),
        ("fan_a", "join"),
        ("fan_b", "join"),
    }


def test_parse_opaque_operator() -> None:
    source = (Path(__file__).parent / "corpus" / "t2_opaque_operator.py").read_text()
    graph, warnings = parse_graph(source)
    mystery = next(n for n in graph.nodes if n.id == "mystery")
    assert mystery.opaque is True
    assert mystery.block_id == "opaque"
    assert "ShinyCustomOperator" in str(mystery.params["code"])
    assert any("mystery" in w for w in warnings)
    assert ("known", "mystery") in {(e.source, e.target) for e in graph.edges}


def test_parse_rejects_non_dag_file() -> None:
    with pytest.raises(ParseError):
        parse_graph("x = 1\n")


def _mutate(source: str) -> GraphModel:
    graph, _ = parse_graph(source)
    return graph


def test_param_change_preserves_rest_of_file() -> None:
    source = (Path(__file__).parent / "corpus" / "t2_dag_decorator.py").read_text()
    graph = _mutate(source)
    for node in graph.nodes:
        if node.id == "extract":
            node.params["bash_command"] = "echo CHANGED"
    result = generate_source(graph, base_source=source)
    assert "echo CHANGED" in result
    # untouched lines survive byte-for-byte
    assert "# entry point marker" in result
    assert '        return "transformed"  # trailing comment survives round-trip' in result
    assert "start >> extract >> transform() >> load" in result
    reparsed, _ = parse_graph(result)
    extract = next(n for n in reparsed.nodes if n.id == "extract")
    assert extract.params["bash_command"] == "echo CHANGED"


def test_add_node_and_edge() -> None:
    source = (Path(__file__).parent / "corpus" / "t2_dag_decorator.py").read_text()
    graph = _mutate(source)
    graph.nodes.append(
        TaskNode(id="notify", block_id="bash", params={"bash_command": "echo notify"})
    )
    graph.edges.append(Edge(source="load", target="notify"))
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert 'task_id="notify"' in result
    # comments survive even though the dependency section was canonicalized
    assert "# entry point marker" in result
    reparsed, _ = parse_graph(result)
    assert {(e.source, e.target) for e in reparsed.edges} == {
        ("start", "extract"),
        ("extract", "transform"),
        ("transform", "load"),
        ("load", "notify"),
    }


def test_remove_node() -> None:
    source = (Path(__file__).parent / "corpus" / "t2_with_dag.py").read_text()
    graph = _mutate(source)
    graph.nodes = [n for n in graph.nodes if n.id != "fan_b"]
    graph.edges = [e for e in graph.edges if "fan_b" not in (e.source, e.target)]
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "fan_b" not in result
    reparsed, _ = parse_graph(result)
    assert {n.id for n in reparsed.nodes} == {"begin", "fan_a", "join"}
    assert {(e.source, e.target) for e in reparsed.edges} == {
        ("begin", "fan_a"),
        ("fan_a", "join"),
    }


def test_meta_change() -> None:
    source = (Path(__file__).parent / "corpus" / "t2_dag_decorator.py").read_text()
    graph = _mutate(source)
    graph.dag.schedule = "@weekly"
    graph.dag.tags = ["dagsmith-dev", "prod"]
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "schedule='@weekly'" in result
    assert "'prod'" in result
    reparsed, _ = parse_graph(result)
    assert reparsed.dag.schedule == "@weekly"
    assert reparsed.dag.tags == ["dagsmith-dev", "prod"]


def test_python_body_change() -> None:
    source = (Path(__file__).parent / "corpus" / "t2_dag_decorator.py").read_text()
    graph = _mutate(source)
    for node in graph.nodes:
        if node.id == "transform":
            node.params["body"] = 'print("new body")\nreturn "v2"'
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert 'print("new body")' in result
    assert "# entry point marker" in result
    reparsed, _ = parse_graph(result)
    body = str(next(n for n in reparsed.nodes if n.id == "transform").params["body"])
    assert 'return "v2"' in body


def test_edit_opaque_via_transform_keeps_it() -> None:
    source = (Path(__file__).parent / "corpus" / "t2_opaque_operator.py").read_text()
    graph = _mutate(source)
    for node in graph.nodes:
        if node.id == "known":
            node.params["bash_command"] = "echo updated"
    result = generate_source(graph, base_source=source)
    assert "ShinyCustomOperator(task_id=\"mystery\", magic_level=11)" in result
    assert "echo updated" in result


def test_parse_endpoint(api_client) -> None:
    source = (Path(__file__).parent / "corpus" / "t2_dag_decorator.py").read_text()
    response = api_client.post("/api/v1/parse", json={"source": source})
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["graph"]["dag"]["dag_id"] == "example_etl"

    broken = api_client.post("/api/v1/parse", json={"source": "def broken(:"})
    assert broken.status_code == 200
    assert broken.json()["graph"] is None
    assert "Syntax error" in broken.json()["error"]


def test_codegen_endpoint_with_base_source(api_client) -> None:
    source = (Path(__file__).parent / "corpus" / "t2_dag_decorator.py").read_text()
    graph, _ = parse_graph(source)
    payload = {"graph": graph.model_dump(), "base_source": source}
    response = api_client.post("/api/v1/codegen", json=payload)
    assert response.status_code == 200
    assert response.json()["source"] == source
