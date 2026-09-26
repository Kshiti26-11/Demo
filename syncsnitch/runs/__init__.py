"""Runs package: write the run artifact (web/runs/<run_id>.json) that the demo website replays."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MAX_DIFF_BYTES = 200 * 1024

# (id, name, type, artefact that proves the step ran)
STEPS = [
    ("S1", "Detect contract drift", "deterministic", "drift.json"),
    ("S2", "Trace consumer usages", "deterministic", "candidates.json"),
    ("S3", "Schema Diff & AST Tracer", "ai", "impact.json"),
    ("S4", "Downstream Code Transformer", "ai", "<diff>"),
    ("S5", "Verify in mock containers", "deterministic", "verification.json"),
    ("S6", "Contract Verifier", "ai", "verdict.json"),
    ("S7", "Human approval", "human", "<companion>"),
    ("S8", "Open draft companion PR", "deterministic", "<companion>"),
    ("S9", "Write run artifact", "deterministic", None),
]


def _git(consumer: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(consumer), *args], capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def write_run_artifact(
    run_id: str,
    runs_dir: str | Path,
    consumer: str | Path,
    branch: str,
    base_branch: str = "main",
    upstream_pr_url: str | None = None,
    companion_pr_url: str | None = None,
    bob_export: str | None = None,
    out_dir: str | Path = Path("web/runs"),
) -> Path:
    """Write <out_dir>/<run_id>.json from the run's JSON files plus the consumer diff; return its path."""
    run_dir = Path(runs_dir) / run_id
    consumer = Path(consumer)

    def load(name: str):
        p = run_dir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    # --relative keeps paths relative to the consumer folder (and scoped to it inside a monorepo)
    diff = _git(consumer, "diff", "--relative", f"{base_branch}...{branch}")
    diffstat = _git(consumer, "diff", "--relative", "--stat", f"{base_branch}...{branch}")
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES:
        diff = diff.encode("utf-8")[:MAX_DIFF_BYTES].decode("utf-8", errors="ignore") + "\n... (truncated)\n"

    def done(proof: str | None) -> bool:
        if proof is None:
            return True
        if proof == "<diff>":
            return bool(diff)
        if proof == "<companion>":
            return bool(companion_pr_url)
        return (run_dir / proof).exists()

    artifact = {
        "run_id": run_id,
        "created_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "upstream_pr_url": upstream_pr_url,
        "companion_pr_url": companion_pr_url,
        "branch": branch,
        "drift": load("drift.json"),
        "candidates": load("candidates.json"),
        "impact": load("impact.json"),
        "verification": load("verification.json"),
        "verdict": load("verdict.json"),
        "diff": diff,
        "diffstat": diffstat,
        "steps": [
            {"id": sid, "name": name, "type": kind, "status": "done" if done(proof) else "skipped"}
            for sid, name, kind, proof in STEPS
        ],
        "bob_session_export": bob_export,
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.json"
    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return out_path
