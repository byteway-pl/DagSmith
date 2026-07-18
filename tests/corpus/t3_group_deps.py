# Dependencies to/from a TaskGroup (group as a dependency endpoint).
from __future__ import annotations

from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import DAG, TaskGroup

with DAG("group_deps", schedule=None):
    start = EmptyOperator(task_id="start")

    with TaskGroup("etl") as etl:
        extract = EmptyOperator(task_id="extract")
        load = EmptyOperator(task_id="load")

    end = EmptyOperator(task_id="end")

    start >> etl >> end
