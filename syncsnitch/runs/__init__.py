"""Runs package: write run artifacts for the demo website."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def write_run_artifact(
    run_id: str,
    runs_dir: str | Path,
    web_runs_dir: str | Path,
    upstream_pr_url: str = "",
    companion_pr_url: str = "",
    branch: str = "",
    diff: str = "",
    diffstat: str = "",
    steps: dict | None = None,
    bob_session_export: str = "",
) -> dict:
    """
    Write the run artifact JSON to web/runs/<run_id>.json.

    Loads drift, candidates, impact, verification, verdict from runs_dir/<run_id>/.
    Trims diff to max 200 KB.
    """
    run_dir = Path(runs_dir) / run_id

    def _load(name: str) -> dict | list | None:
        p = run_dir / name
        if p.exists():
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        return None

    drift = _load("drift.json")
    candidates = _load("candidates.json")
    impact = _load("impact.json")
    verification = _load("verification.json")
    verdict = _load("verdict.json")

    # Trim diff to 200 KB
    max_diff_bytes = 200 * 1024
    if len(diff.encode("utf-8")) > max_diff_bytes:
        diff = diff.encode("utf-8")[:max_diff_bytes].decode("utf-8", errors="replace")

    artifact = {
        "run_id": run_id,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "upstream_pr_url": upstream_pr_url,
        "companion_pr_url": companion_pr_url,
        "branch": branch,
        "drift": drift,
        "candidates": candidates,
        "impact": impact,
        "verification": verification,
        "verdict": verdict,
        "diff": diff,
        "diffstat": diffstat,
        "steps": steps or {},
        "bob_session_export": bob_session_export,
    }

    out_dir = Path(web_runs_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2)

    return artifact
