# Classic `with DAG(...)` style with lists and << chains.
from __future__ import annotations

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import DAG

with DAG(
    "legacy_style",
    schedule="@hourly",
    description="Hand written, oddly formatted",
    tags=["legacy", "etl"],
):
    begin = EmptyOperator(task_id="begin")
    fan_a = BashOperator(task_id="fan_a", bash_command="echo a")
    fan_b = BashOperator(
        task_id="fan_b",
        bash_command="echo b",
        retries=1,
    )
    join = EmptyOperator(task_id="join")

    begin >> [fan_a, fan_b]
    join << fan_a
    join << fan_b
