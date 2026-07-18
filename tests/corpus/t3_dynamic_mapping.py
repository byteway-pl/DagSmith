# Dynamic task mapping: taskflow .expand() and Operator.partial().expand().
from __future__ import annotations

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task


@dag(schedule=None, tags=["t3"])
def mapped_dag():
    @task
    def add_one(x: int) -> int:
        return x + 1

    added = add_one.expand(x=[1, 2, 3])

    shouter = BashOperator.partial(task_id="shout", retries=1).expand(
        bash_command=["echo a", "echo b"]
    )

    added >> shouter


mapped_dag()
