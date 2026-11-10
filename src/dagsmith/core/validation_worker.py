"""Subprocess entry point for the import-stage validation.

Reads DAG source from stdin, loads it through ``DagBag`` (like the
dag-processor would) and prints a JSON result to stdout. Runs in its own
process so user code never executes inside the api-server.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile


def main() -> int:
    source = sys.stdin.read()
    os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")

    errors: list[dict[str, object]] = []
    dag_count = 0
    with tempfile.TemporaryDirectory(prefix="dagsmith-validate-") as tmp_dir:
        candidate = os.path.join(tmp_dir, "candidate.py")
        with open(candidate, "w", encoding="utf-8") as fh:
            fh.write(source)

        try:
            from airflow.dag_processing.dagbag import DagBag
        except ModuleNotFoundError as exc:
            # Airflow 3.1/3.2 keep DagBag in models. Do not hide missing
            # dependencies inside the new module by falling back for those.
            if exc.name != "airflow.dag_processing.dagbag":
                raise
            from airflow.models.dagbag import DagBag

        # Airflow 3.3 removed include_examples; older releases still need it
        # explicitly disabled, regardless of the host's load_examples setting.
        kwargs = {}
        if "include_examples" in inspect.signature(DagBag).parameters:
            kwargs["include_examples"] = False
        # Only this short-lived worker receives the DAG import context.
        sys.path[:0] = sys.argv[1:]
        bag = DagBag(dag_folder=tmp_dir, safe_mode=False, **kwargs)
        dag_count = len(bag.dags)
        for _file, message in bag.import_errors.items():
            errors.append({"line": None, "message": str(message)})

    json.dump({"errors": errors, "dag_count": dag_count}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
