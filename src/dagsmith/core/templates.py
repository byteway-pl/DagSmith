"""Built-in DAG starters. Rendering never executes template code."""

from __future__ import annotations

_BODIES = {
    "blank": ("", "    pass\n"),
    "bash": (
        "from airflow.providers.standard.operators.bash import BashOperator\n",
        '    extract = BashOperator(task_id="extract", bash_command="echo extract")\n'
        '    transform = BashOperator(task_id="transform", bash_command="echo transform")\n'
        '    load = BashOperator(task_id="load", bash_command="echo load")\n'
        "    extract >> transform >> load\n",
    ),
    "parallel": (
        "from airflow.providers.standard.operators.empty import EmptyOperator\n",
        '    start = EmptyOperator(task_id="start")\n'
        '    left = EmptyOperator(task_id="left")\n'
        '    right = EmptyOperator(task_id="right")\n'
        '    finish = EmptyOperator(task_id="finish")\n'
        "    start >> [left, right] >> finish\n",
    ),
    "taskflow": (
        "from airflow.sdk import task\n",
        "    @task\n"
        "    def extract():\n"
        "        return [1, 2, 3]\n\n"
        "    @task\n"
        "    def transform(values):\n"
        "        return [value * 2 for value in values]\n\n"
        "    @task\n"
        "    def load(values):\n"
        "        print(values)\n\n"
        "    load(transform(extract()))\n",
    ),
}


def render_template(template_id: str, dag_id: str, tags: list[str]) -> str:
    if template_id not in _BODIES:
        from dagsmith.api.errors import BadRequestError

        raise BadRequestError("Unknown DAG template")
    imports, body = _BODIES[template_id]
    return (
        '# dagsmith: v1\n"""DAG created with DagSmith."""\n\n'
        "from __future__ import annotations\n\n"
        "from airflow.sdk import dag\n"
        f"{imports}\n\n"
        f"@dag(dag_id={dag_id!r}, schedule=None, catchup=False, tags={tags!r})\n"
        f"def {dag_id}():\n{body}\n\n{dag_id}()\n"
    )


def owned_template(session, template_id, username):
    from dagsmith.api.errors import NotFoundError
    from dagsmith.core.db import DagTemplate

    template = session.get(DagTemplate, template_id)
    if template is None or not username or template.owner != username:
        raise NotFoundError("Template not found")
    return template


def render_custom(source: str, dag_id: str, tags: list[str]) -> str:
    return source.replace("{{dag_id}}", dag_id).replace("{{tags}}", repr(tags))
