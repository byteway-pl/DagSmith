"""Optional git integration for deploys.

When the target bundle root is a git repository and ``[dagsmith] git_commit``
is enabled, every deploy commits the written file (author = the deploying
user); ``git_push`` additionally pushes the current branch. Git failures never
roll back a deploy — the file is already safely on disk — they are reported in
the deploy result and the audit log instead.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from dagsmith.core.storage import BundleRef

log = logging.getLogger(__name__)

_GIT_TIMEOUT = 30


@dataclass
class GitResult:
    commit_sha: str | None = None
    pushed: bool = False
    error: str | None = None


def _git(bundle_root: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", bundle_root, *args],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT,
    )


def is_git_repo(bundle: BundleRef) -> bool:
    try:
        proc = _git(str(bundle.root), "rev-parse", "--is-inside-work-tree")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _normalize_remote(url: str) -> str | None:
    if url.startswith("git@"):
        host, _, path = url.removeprefix("git@").partition(":")
        url = f"https://{host}/{path}"
    url = url.removesuffix(".git")
    return url if url.startswith("http") else None


def remote_commit_url(
    bundle: BundleRef, sha: str, remote_url: str | None = None
) -> str | None:
    """Web URL of a commit for github/gitlab-style remotes (best effort)."""
    if remote_url is None:
        try:
            proc = _git(str(bundle.root), "remote", "get-url", "origin")
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        remote_url = proc.stdout.strip()
    url = _normalize_remote(remote_url)
    if url is None:
        return None
    if "gitlab" in url:
        return f"{url}/-/commit/{sha}"
    return f"{url}/commit/{sha}"


def push_head(
    bundle: BundleRef, remote_url: str | None, branch: str | None
) -> tuple[bool, str | None]:
    """Push HEAD — to `remote_url HEAD:branch` when a team target is set,
    otherwise a plain `git push` to the checkout's upstream. Never raises."""
    root = str(bundle.root)
    try:
        if remote_url:
            args = ["push", remote_url, f"HEAD:refs/heads/{branch or 'main'}"]
        else:
            args = ["push"]
        proc = _git(root, *args)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git push failed: {exc}"
    if proc.returncode != 0:
        return False, f"git push failed: {proc.stderr.strip()[:500]}"
    return True, None


def commit_deploy(
    bundle: BundleRef, rel_path: str, user: str | None, message: str, push: bool
) -> GitResult:
    """Commit (and optionally push) a deployed file. Never raises."""
    root = str(bundle.root)
    author_name = user or "dagsmith"
    author_email = f"{author_name}@dagsmith.local"
    try:
        add = _git(root, "add", "--", rel_path)
        if add.returncode != 0:
            return GitResult(error=f"git add failed: {add.stderr.strip()[:500]}")
        commit = _git(
            root,
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            message,
            "--",
            rel_path,
        )
        no_changes = False
        if commit.returncode != 0:
            output = (commit.stdout + commit.stderr).strip()
            if "nothing to commit" in output or "no changes added to commit" in output:
                # The file is already committed (e.g. deploy committed it) —
                # not an error; a requested push still pushes HEAD.
                no_changes = True
            else:
                return GitResult(error=f"git commit failed: {output[:500]}")
        del no_changes  # HEAD sha is reported either way
        sha_proc = _git(root, "rev-parse", "HEAD")
        sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
        result = GitResult(commit_sha=sha)
        if push:
            pushed, push_error = push_head(bundle, None, None)
            result.pushed = pushed
            if push_error:
                result.error = push_error
        return result
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("Git operation failed for %s: %s", rel_path, exc)
        return GitResult(error=f"git unavailable: {exc}")
