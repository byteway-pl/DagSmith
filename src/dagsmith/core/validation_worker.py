"""Subprocess entry point for the import-stage validation.

Reads DAG source from stdin, loads it through ``DagBag`` (like the
dag-processor would) and prints a JSON result to stdout. Runs in its own
process so user code never executes inside the api-server.
"""

from __future__ import annotations

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

        from airflow.models.dagbag import DagBag

        bag = DagBag(dag_folder=tmp_dir, include_examples=False, safe_mode=False)
        dag_count = len(bag.dags)
        for _file, message in bag.import_errors.items():
            errors.append({"line": None, "message": str(message)})

    json.dump({"errors": errors, "dag_count": dag_count}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
