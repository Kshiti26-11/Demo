from datetime import UTC, datetime
from pathlib import Path
import subprocess


def run(args: list[str], cwd: str | Path | None = None) -> str:
    res = subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)
    return res.stdout


def resolve_ref(repo: str | Path, ref: str) -> str:
    try:
        out = run(["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"])
        return out.strip()
    except subprocess.CalledProcessError:
        out = run(["git", "-C", str(repo), "rev-parse", "--verify", f"origin/{ref}^{{commit}}"])
        return out.strip()


def show_file(repo: str | Path, sha: str, path: str) -> str | None:
    # Use forward slashes for git path
    posix_path = Path(path).as_posix()
    try:
        return run(["git", "-C", str(repo), "show", f"{sha}:{posix_path}"])
    except subprocess.CalledProcessError:
        return None


def added_files(repo: str | Path, base_sha: str, head_sha: str, pathspec: str) -> list[str]:
    posix_spec = Path(pathspec).as_posix()
    try:
        out = run(["git", "-C", str(repo), "diff", "--name-only", "--diff-filter=A", base_sha, head_sha, "--", posix_spec])
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        return lines
    except subprocess.CalledProcessError:
        return []


def new_run_id() -> str:
    return "r-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
