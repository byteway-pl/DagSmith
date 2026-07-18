"""Live DAG files: bundle discovery, path safety, reads, and the deploy write path.

Every path coming from a request goes through :func:`safe_resolve`; nothing in
this module ever touches a file outside a bundle root. Writes happen only via
:func:`write_file_atomic`, which is called exclusively by the deploy flow.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dagsmith.api.errors import BadRequestError, ForbiddenError, NotFoundError
from dagsmith.config import get_int, get_list


@dataclass(frozen=True)
class BundleRef:
    name: str
    root: Path
    writable: bool


def dagsmith_home() -> Path:
    """Working directory for backups and the audit log."""
    airflow_home = os.environ.get("AIRFLOW_HOME", str(Path.home() / "airflow"))
    home = Path(airflow_home) / "dagsmith"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _bundle_allowed(name: str) -> bool:
    allowed = get_list("allowed_bundles")
    return allowed == ["*"] or name in allowed


def list_bundles() -> list[BundleRef]:
    """Bundles with a local filesystem path, as seen from the api-server."""
    from airflow.dag_processing.bundles.manager import DagBundlesManager

    bundles: list[BundleRef] = []
    for bundle in DagBundlesManager().get_all_dag_bundles():
        path = getattr(bundle, "path", None)
        if path is None:
            continue
        root = Path(path)
        writable = (
            root.is_dir() and os.access(root, os.W_OK) and _bundle_allowed(bundle.name)
        )
        bundles.append(BundleRef(name=bundle.name, root=root.resolve(), writable=writable))
    return bundles


def get_bundle(name: str) -> BundleRef:
    for bundle in list_bundles():
        if bundle.name == name:
            return bundle
    raise NotFoundError(f"Unknown bundle: {name}")


def safe_resolve(bundle: BundleRef, rel_path: str, must_exist: bool = True) -> Path:
    """Resolve ``rel_path`` inside the bundle root, rejecting any escape attempt."""
    if not rel_path or rel_path.startswith(("/", "\\")) or ".." in Path(rel_path).parts:
        raise BadRequestError(f"Invalid path: {rel_path}")
    candidate = (bundle.root / rel_path).resolve()
    root = bundle.root.resolve()
    if not candidate.is_relative_to(root):
        raise ForbiddenError(f"Path escapes bundle root: {rel_path}")
    if must_exist and not candidate.is_file():
        raise NotFoundError(f"File not found: {rel_path}")
    return candidate


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def list_py_files(bundle: BundleRef) -> list[tuple[str, int, datetime]]:
    results: list[tuple[str, int, datetime]] = []
    if not bundle.root.is_dir():
        return results
    for path in sorted(bundle.root.rglob("*.py")):
        if not path.is_file() or any(part.startswith(".") for part in path.parts):
            continue
        stat = path.stat()
        results.append(
            (
                str(path.relative_to(bundle.root)),
                stat.st_size,
                datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            )
        )
    return results


def read_file(bundle: BundleRef, rel_path: str) -> tuple[str, str, datetime]:
    path = safe_resolve(bundle, rel_path)
    content = path.read_text(encoding="utf-8")
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return content, content_hash(content), mtime


def file_hash_or_none(bundle: BundleRef, rel_path: str) -> str | None:
    """Hash of the live file, or None when it does not exist."""
    path = safe_resolve(bundle, rel_path, must_exist=False)
    if not path.is_file():
        return None
    return content_hash(path.read_text(encoding="utf-8"))


def backup_file(bundle: BundleRef, rel_path: str) -> str | None:
    """Copy the live file aside before a deploy overwrites it. Returns backup path."""
    path = safe_resolve(bundle, rel_path, must_exist=False)
    if not path.is_file():
        return None
    backup_dir = dagsmith_home() / "backups" / bundle.name / rel_path
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    digest = content_hash(path.read_text(encoding="utf-8"))[:8]
    backup_path = backup_dir / f"{stamp}_{digest}.py"
    shutil.copy2(path, backup_path)
    _prune_backups(backup_dir)
    return str(backup_path)


def _prune_backups(backup_dir: Path) -> None:
    keep = get_int("backup_retention")
    backups = sorted(backup_dir.glob("*.py"))
    for old in backups[: max(0, len(backups) - keep)]:
        old.unlink(missing_ok=True)


def write_file_atomic(bundle: BundleRef, rel_path: str, content: str) -> str:
    """Deploy write: atomic replace within the bundle. Returns the new content hash."""
    if not bundle.writable:
        raise ForbiddenError(f"Bundle is not writable: {bundle.name}")
    path = safe_resolve(bundle, rel_path, must_exist=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.dagsmith-tmp"
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    return content_hash(content)
