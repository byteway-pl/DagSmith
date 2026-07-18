# Two DAGs in one file: DagSmith edits the first, warns about the rest.
from __future__ import annotations

from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import DAG

with DAG("first_dag", schedule=None):
    a = EmptyOperator(task_id="a")

with DAG("second_dag", schedule="@daily"):
    b = EmptyOperator(task_id="b")
