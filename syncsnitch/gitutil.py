"""Git utility functions for SyncSnitch (read-only / engine-support only).

Every path is relative to the directory passed as ``repo``. That directory may be a repository root
(separate orders-service / billing-service repos) or a sub-folder of a monorepo (kshiti26-11/demo with
orders-service/ and billing-service/ inside it): ``git show <sha>:./<path>`` and ``git diff --relative``
resolve paths against the working directory instead of the repository root.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


def run(args: list[str], cwd: str | Path | None = None) -> str:
    """Run a command (check=True) and return its stdout."""
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def resolve_ref(repo: str | Path, ref: str) -> str:
    """Resolve a branch, tag or sha to a commit sha (tries <ref>, then origin/<ref>)."""
    for candidate in (ref, f"origin/{ref}"):
        try:
            return run(["git", "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"], cwd=repo).strip()
        except subprocess.CalledProcessError:
            continue
    raise ValueError(f"cannot resolve git ref {ref!r} in {repo}")


def show_file(repo: str | Path, sha: str, path: str) -> str | None:
    """Return the file content at <sha>, or None when the file does not exist there."""
    try:
        return run(["git", "show", f"{sha}:./{path}"], cwd=repo)
    except subprocess.CalledProcessError:
        return None


def added_files(repo: str | Path, base_sha: str, head_sha: str, pathspec: str) -> list[str]:
    """Paths (relative to ``repo``) of files ADDED between base and head that match ``pathspec``."""
    out = run(
        ["git", "diff", "--relative", "--name-only", "--diff-filter=A", base_sha, head_sha, "--", pathspec],
        cwd=repo,
    )
    return sorted(p.strip() for p in out.splitlines() if p.strip())


def new_run_id() -> str:
    """Return a new run ID in the format r-YYYYMMDD-HHMMSS (UTC)."""
    return datetime.now(tz=timezone.utc).strftime("r-%Y%m%d-%H%M%S")
