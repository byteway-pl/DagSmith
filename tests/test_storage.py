from __future__ import annotations

from pathlib import Path

import pytest

from dagsmith.api.errors import BadRequestError, ForbiddenError, NotFoundError
from dagsmith.core import storage


def _bundle(root: Path, writable: bool = True) -> storage.BundleRef:
    return storage.BundleRef(name="test", root=root.resolve(), writable=writable)


def test_safe_resolve_rejects_escapes(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    with pytest.raises(BadRequestError):
        storage.safe_resolve(bundle, "/etc/passwd")
    with pytest.raises(BadRequestError):
        storage.safe_resolve(bundle, "../outside.py")
    with pytest.raises(BadRequestError):
        storage.safe_resolve(bundle, "a/../../outside.py")
    with pytest.raises(NotFoundError):
        storage.safe_resolve(bundle, "missing.py")


def test_safe_resolve_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "dags"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("x = 1")
    (root / "link").symlink_to(outside)
    with pytest.raises(ForbiddenError):
        storage.safe_resolve(_bundle(root), "link/secret.py")


def test_atomic_write_and_read_roundtrip(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    digest = storage.write_file_atomic(bundle, "sub/dir/new_dag.py", "print('hi')\n")
    content, read_digest, _ = storage.read_file(bundle, "sub/dir/new_dag.py")
    assert content == "print('hi')\n"
    assert digest == read_digest == storage.content_hash(content)


def test_write_refused_on_readonly_bundle(tmp_path: Path) -> None:
    with pytest.raises(ForbiddenError):
        storage.write_file_atomic(_bundle(tmp_path, writable=False), "a.py", "x")


def test_backup_and_prune(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRFLOW__DAGSMITH__BACKUP_RETENTION", "2")
    bundle = _bundle(tmp_path)
    backups = []
    for i in range(4):
        storage.write_file_atomic(bundle, "dag.py", f"v = {i}\n")
        backups.append(storage.backup_file(bundle, "dag.py"))
    backup_dir = Path(backups[-1]).parent
    remaining = sorted(backup_dir.glob("*.py"))
    assert len(remaining) == 2


def test_list_py_files_skips_hidden(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (tmp_path / "visible.py").write_text("a = 1")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "h.py").write_text("b = 2")
    files = storage.list_py_files(bundle)
    assert [f[0] for f in files] == ["visible.py"]


def test_file_hash_or_none(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    assert storage.file_hash_or_none(bundle, "nope.py") is None
    storage.write_file_atomic(bundle, "yes.py", "x = 1\n")
    assert storage.file_hash_or_none(bundle, "yes.py") == storage.content_hash("x = 1\n")
