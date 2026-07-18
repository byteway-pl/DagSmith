# Loops creating tasks and nested TaskGroups.
from __future__ import annotations

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import DAG
from airflow.sdk import TaskGroup

with DAG("looped", schedule=None):
    start = EmptyOperator(task_id="start")

    with TaskGroup("etl") as etl:
        extract = BashOperator(task_id="extract", bash_command="echo e")

        with TaskGroup("transforms"):
            t1 = BashOperator(task_id="t1", bash_command="echo t1")
            t2 = BashOperator(task_id="t2", bash_command="echo t2")

        extract >> [t1, t2]

    # dynamically generated report tasks
    for i in range(3):
        BashOperator(task_id=f"report_{i}", bash_command=f"echo report {i}")

    start >> extract
