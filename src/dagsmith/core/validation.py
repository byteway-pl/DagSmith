"""DAG source validation.

Two stages:
1. syntax  — ``ast.parse`` in-process (never executes user code),
2. import  — executes the file the same way the dag-processor would, but in an
   isolated subprocess with a timeout (see ``validation_worker.py``). User code
   is NEVER executed in the api-server process.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys

from dagsmith.api.schemas import ValidateResult, ValidationIssue
from dagsmith.config import get_int


def check_syntax(source: str) -> list[ValidationIssue]:
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return [
            ValidationIssue(
                line=exc.lineno,
                col=exc.offset,
                message=exc.msg or "Syntax error",
                kind="syntax",
            )
        ]
    return []


def check_import(source: str) -> tuple[list[ValidationIssue], int | None]:
    """Run the import check in a subprocess. Returns (issues, dag_count)."""
    timeout = get_int("validation_timeout")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "dagsmith.core.validation_worker"],
            input=source,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (
            [
                ValidationIssue(
                    message=f"Validation timed out after {timeout}s", kind="timeout"
                )
            ],
            None,
        )

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        return (
            [ValidationIssue(message=f"Validation worker failed: {detail}", kind="import")],
            None,
        )

    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    issues = [
        ValidationIssue(line=e.get("line"), message=e["message"], kind="import")
        for e in payload["errors"]
    ]
    return issues, payload.get("dag_count")


def validate_source(source: str, deep: bool = True) -> ValidateResult:
    issues = check_syntax(source)
    if issues:
        return ValidateResult(ok=False, errors=issues)

    dag_count: int | None = None
    if deep:
        import_issues, dag_count = check_import(source)
        issues.extend(import_issues)
        if dag_count == 0 and not issues:
            issues.append(
                ValidationIssue(message="File defines no DAG", kind="dag")
            )
    return ValidateResult(ok=not issues, errors=issues, dag_count=dag_count)
