# Contains an operator DagSmith does not know -> opaque node.
from __future__ import annotations

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag

from some.provider import ShinyCustomOperator


@dag(schedule=None)
def with_custom():
    known = BashOperator(task_id="known", bash_command="echo ok")
    mystery = ShinyCustomOperator(task_id="mystery", magic_level=11)

    known >> mystery


with_custom()
