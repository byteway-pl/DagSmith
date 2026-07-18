# A hand-written DAG in @dag/@task style, with comments and custom formatting.
from __future__ import annotations

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import dag, task


@dag(schedule=None, tags=["dagsmith-dev"])
def example_etl():
    # entry point marker
    start = EmptyOperator(task_id="start")

    extract = BashOperator(task_id="extract", bash_command="echo extracting")

    @task
    def transform() -> str:
        return "transformed"  # trailing comment survives round-trip

    load = BashOperator(task_id="load", bash_command="echo loading")

    start >> extract >> transform() >> load


example_etl()
