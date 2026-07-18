"""T3 parsing (dynamic constructs, task groups) and transforms inside groups."""

from __future__ import annotations

import ast
from pathlib import Path

from dagsmith.core.codegen import generate_source
from dagsmith.core.parser import parse_graph

CORPUS = Path(__file__).parent / "corpus"


def test_dynamic_mapping_parses() -> None:
    graph, warnings = parse_graph((CORPUS / "t3_dynamic_mapping.py").read_text())
    by_id = {n.id: n for n in graph.nodes}
    # taskflow with .expand() stays an editable python node
    assert by_id["add_one"].block_id == "python"
    assert by_id["add_one"].opaque is False
    # Operator.partial().expand() becomes opaque, id from partial(task_id=...)
    assert by_id["shout"].opaque is True
    assert "partial" in str(by_id["shout"].params["code"])
    assert {(e.source, e.target) for e in graph.edges} == {("add_one", "shout")}


def test_loops_and_nested_groups_parse() -> None:
    graph, warnings = parse_graph((CORPUS / "t3_loops_and_groups.py").read_text())
    by_id = {n.id: n for n in graph.nodes}

    assert {g.id for g in graph.groups} == {"etl", "etl.transforms"}
    nested = next(g for g in graph.groups if g.id == "etl.transforms")
    assert nested.parent_id == "etl"

    assert by_id["start"].group_id is None
    assert by_id["extract"].group_id == "etl"
    assert by_id["t1"].group_id == "etl.transforms"

    # the for-loop shows up as one opaque code block
    regions = [n for n in graph.nodes if n.id.startswith("code_block_")]
    assert len(regions) == 1
    assert regions[0].opaque is True
    assert "for i in range(3):" in str(regions[0].params["code"])
    assert any("code-only block" in w for w in warnings)

    assert {(e.source, e.target) for e in graph.edges} == {
        ("extract", "t1"),
        ("extract", "t2"),
        ("start", "extract"),
    }


def test_multiple_dags_warns_and_edits_first() -> None:
    graph, warnings = parse_graph((CORPUS / "t3_multiple_dags.py").read_text())
    assert graph.dag.dag_id == "first_dag"
    assert [n.id for n in graph.nodes] == ["a"]
    assert any("2 DAGs" in w for w in warnings)


def test_param_edit_inside_nested_group() -> None:
    source = (CORPUS / "t3_loops_and_groups.py").read_text()
    graph, _ = parse_graph(source)
    for node in graph.nodes:
        if node.id == "t1":
            node.params["bash_command"] = "echo T1-EDITED"
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "echo T1-EDITED" in result
    # everything else untouched, including the loop and the sibling task
    assert 'BashOperator(task_id=f"report_{i}", bash_command=f"echo report {i}")' in result
    assert 'BashOperator(task_id="t2", bash_command="echo t2")' in result
    assert "# dynamically generated report tasks" in result
    reparsed, _ = parse_graph(result)
    t1 = next(n for n in reparsed.nodes if n.id == "t1")
    assert t1.params["bash_command"] == "echo T1-EDITED"
    assert t1.group_id == "etl.transforms"


def test_remove_task_inside_group() -> None:
    source = (CORPUS / "t3_loops_and_groups.py").read_text()
    graph, _ = parse_graph(source)
    graph.nodes = [n for n in graph.nodes if n.id != "t2"]
    graph.edges = [e for e in graph.edges if "t2" not in (e.source, e.target)]
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert 'task_id="t2"' not in result
    reparsed, _ = parse_graph(result)
    assert "t2" not in {n.id for n in reparsed.nodes}
    # group structure survives
    assert {g.id for g in reparsed.groups} == {"etl", "etl.transforms"}


def test_python_body_edit_on_mapped_task() -> None:
    source = (CORPUS / "t3_dynamic_mapping.py").read_text()
    graph, _ = parse_graph(source)
    for node in graph.nodes:
        if node.id == "add_one":
            node.params["body"] = "return x + 100"
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "return x + 100" in result
    # the .expand() call site is untouched
    assert "added = add_one.expand(x=[1, 2, 3])" in result
