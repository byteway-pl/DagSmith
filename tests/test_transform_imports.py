"""Adding a task via transform must add its import (else validation fails)."""

from __future__ import annotations

import ast

from dagsmith.core.codegen import generate_source
from dagsmith.core.model import TaskNode
from dagsmith.core.parser import parse_graph

BASE = '''\
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import dag


@dag(schedule=None)
def d():
    start = EmptyOperator(task_id="start")


d()
'''


def test_added_operator_gets_its_import() -> None:
    graph, _ = parse_graph(BASE)
    graph.nodes.append(
        TaskNode(id="runner", block_id="bash", params={"bash_command": "echo hi"})
    )
    result = generate_source(graph, base_source=BASE)
    ast.parse(result)
    assert "from airflow.providers.standard.operators.bash import BashOperator" in result
    assert 't_runner = BashOperator(task_id="runner"' in result
    # the operator class is now resolvable — reparse succeeds and keeps it typed
    reparsed, _ = parse_graph(result)
    assert next(n for n in reparsed.nodes if n.id == "runner").block_id == "bash"


def test_added_python_task_imports_task() -> None:
    graph, _ = parse_graph(BASE)
    graph.nodes.append(
        TaskNode(id="work", block_id="python", params={"body": "return 1"})
    )
    result = generate_source(graph, base_source=BASE)
    ast.parse(result)
    assert "import task" in result
    assert "def work():" in result


def test_no_duplicate_import_when_already_present() -> None:
    # adding a second bash task must not import BashOperator twice
    graph, _ = parse_graph(BASE)
    graph.nodes.append(
        TaskNode(id="one", block_id="bash", params={"bash_command": "echo 1"})
    )
    once = generate_source(graph, base_source=BASE)
    graph2, _ = parse_graph(once)
    graph2.nodes.append(
        TaskNode(id="two", block_id="bash", params={"bash_command": "echo 2"})
    )
    twice = generate_source(graph2, base_source=once)
    ast.parse(twice)
    assert twice.count("import BashOperator") == 1
