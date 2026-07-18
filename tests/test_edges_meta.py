"""Edge labels, trigger_rule and the extended DAG meta (M6+ polish)."""

from __future__ import annotations

import ast

from dagsmith.core.codegen import generate_source
from dagsmith.core.model import DagMeta, Edge, GraphModel, TaskNode
from dagsmith.core.parser import parse_graph

LABELED_SOURCE = '''\
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Label, dag


@dag(schedule=None)
def labeled():
    a = BashOperator(task_id="a", bash_command="echo a")
    b = BashOperator(task_id="b", bash_command="echo b", trigger_rule="one_failed")

    a >> Label("on data") >> b


labeled()
'''


def test_parse_edge_label_and_trigger_rule() -> None:
    graph, warnings = parse_graph(LABELED_SOURCE)
    assert [(e.source, e.target, e.label) for e in graph.edges] == [("a", "b", "on data")]
    node_b = next(n for n in graph.nodes if n.id == "b")
    assert node_b.params["trigger_rule"] == "one_failed"
    assert warnings == []


def test_label_roundtrip_invariant() -> None:
    graph, _ = parse_graph(LABELED_SOURCE)
    assert generate_source(graph, base_source=LABELED_SOURCE) == LABELED_SOURCE


def test_add_label_via_transform_adds_import() -> None:
    source = LABELED_SOURCE.replace('Label("on data") >> ', "").replace(
        "from airflow.sdk import Label, dag", "from airflow.sdk import dag"
    )
    graph, _ = parse_graph(source)
    graph.edges[0].label = "happy path"
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "Label('happy path')" in result
    assert "from airflow.sdk import Label" in result
    reparsed, _ = parse_graph(result)
    assert reparsed.edges[0].label == "happy path"


def test_set_trigger_rule_via_transform() -> None:
    source = LABELED_SOURCE
    graph, _ = parse_graph(source)
    for node in graph.nodes:
        if node.id == "a":
            node.params["trigger_rule"] = "all_done"
    result = generate_source(graph, base_source=source)
    assert "trigger_rule='all_done'" in result
    # untouched task keeps its original formatting
    assert 'trigger_rule="one_failed"' in result


META_SOURCE = '''\
import pendulum
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import dag


@dag(
    schedule="@daily",
    start_date=pendulum.datetime(2025, 3, 1),
    catchup=False,
    max_active_runs=2,
    default_args={"owner": "data-team", "retries": 3, "custom_thing": [1, 2]},
)
def rich_meta():
    a = EmptyOperator(task_id="a")


rich_meta()
'''


def test_parse_extended_meta() -> None:
    graph, _ = parse_graph(META_SOURCE)
    meta = graph.dag
    assert meta.start_date == "2025-03-01"
    assert meta.catchup is False
    assert meta.max_active_runs == 2
    assert meta.owner == "data-team"
    assert meta.retries == 3


def test_extended_meta_roundtrip_invariant() -> None:
    graph, _ = parse_graph(META_SOURCE)
    assert generate_source(graph, base_source=META_SOURCE) == META_SOURCE


def test_meta_change_preserves_unknown_default_args() -> None:
    graph, _ = parse_graph(META_SOURCE)
    graph.dag.retries = 5
    graph.dag.owner = "platform"
    result = generate_source(graph, base_source=META_SOURCE)
    ast.parse(result)
    assert "'owner': 'platform'" in result
    assert "'retries': 5" in result
    assert '"custom_thing": [1, 2]' in result  # preserved raw extra
    reparsed, _ = parse_graph(result)
    assert reparsed.dag.retries == 5


def test_set_start_date_and_catchup_via_transform() -> None:
    source = LABELED_SOURCE
    graph, _ = parse_graph(source)
    graph.dag.start_date = "2026-01-15"
    graph.dag.catchup = True
    graph.dag.retry_delay_s = 300
    result = generate_source(graph, base_source=source)
    ast.parse(result)
    assert "start_date=pendulum.datetime(2026, 1, 15)" in result
    assert "import pendulum" in result
    assert "catchup=True" in result
    assert "'retry_delay': timedelta(seconds=300)" in result
    assert "from datetime import timedelta" in result


def test_from_scratch_with_full_meta_and_labels() -> None:
    graph = GraphModel(
        dag=DagMeta(
            dag_id="full",
            schedule="@daily",
            start_date="2026-01-01",
            catchup=False,
            max_active_runs=1,
            owner="me",
            email="me@x.io",
            retries=2,
            retry_delay_s=60,
        ),
        nodes=[
            TaskNode(id="a", block_id="empty"),
            TaskNode(id="b", block_id="empty", params={"trigger_rule": "one_success"}),
        ],
        edges=[Edge(source="a", target="b", label="go")],
    )
    source = generate_source(graph)
    ast.parse(source)
    assert "start_date=pendulum.datetime(2026, 1, 1)" in source
    assert "default_args={'owner': 'me', 'email': 'me@x.io', 'retries': 2" in source
    assert "t_a >> Label('go') >> t_b" in source
    assert "trigger_rule='one_success'" in source
    reparsed, _ = parse_graph(source)
    assert reparsed.dag.retry_delay_s == 60
    assert reparsed.edges[0].label == "go"
