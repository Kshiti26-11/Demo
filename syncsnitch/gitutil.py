"""Git utility functions for SyncSnitch (read-only / engine-support only)."""
from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def run(args: list[str], cwd: str | Path | None = None) -> str:
    """Run a git command and return stdout as a string."""
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def resolve_ref(repo: str | Path, ref: str) -> str:
    """Resolve a symbolic ref (branch name, tag, etc.) to a SHA."""
    return run(["git", "rev-parse", ref], cwd=repo).strip()


def show_file(repo: str | Path, sha: str, path: str) -> str:
    """Read a file at a given commit SHA from the repo."""
    return run(["git", "show", f"{sha}:{path}"], cwd=repo)


def added_files(
    repo: str | Path,
    base: str,
    head: str,
    prefix: str = "",
) -> list[str]:
    """
    Return absolute paths of files ADDED between base and head that match prefix.
    Files are extracted to a temp directory (caller is responsible for cleanup).
    """
    diff_output = run(
        ["git", "diff", "--name-only", "--diff-filter=A", base, head, "--", prefix],
        cwd=repo,
    )
    rel_paths = [p.strip() for p in diff_output.splitlines() if p.strip()]
    if not rel_paths:
        return []

    # Extract each file to a temporary directory
    tmpdir = tempfile.mkdtemp(prefix="syncsnitch_mig_")
    result_paths: list[str] = []
    for rel in rel_paths:
        content = show_file(repo, head, rel)
        dest = Path(tmpdir) / Path(rel).name
        dest.write_text(content, encoding="utf-8")
        result_paths.append(str(dest))

    return sorted(result_paths)


def new_run_id() -> str:
    """Return a new run ID in the format r-YYYYMMDD-HHMMSS (UTC)."""
    now = datetime.now(tz=timezone.utc)
    return now.strftime("r-%Y%m%d-%H%M%S")
