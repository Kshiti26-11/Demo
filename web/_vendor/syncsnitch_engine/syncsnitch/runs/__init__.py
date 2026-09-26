from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
from typing import Any


def write_run_artifact(
    run_id: str,
    runs_dir: Path,
    consumer: Path,
    branch: str,
    base_branch: str = "main",
    upstream_pr_url: str | None = None,
    companion_pr_url: str | None = None,
    bob_export: str | None = None,
    out_dir: Path = Path("web/runs"),
) -> Path:
    run_folder = Path(runs_dir) / run_id
    consumer_path = Path(consumer).resolve()

    def read_opt_json(filename: str) -> dict[str, Any] | None:
        p = run_folder / filename
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    drift = read_opt_json("drift.json")
    candidates = read_opt_json("candidates.json")
    impact = read_opt_json("impact.json")
    verification = read_opt_json("verification.json")
    verdict = read_opt_json("verdict.json")

    # git diff
    diff_text = ""
    diffstat = ""
    try:
        res = subprocess.run(
            ["git", "-C", str(consumer_path), "diff", f"{base_branch}...{branch}"],
            capture_output=True,
            text=True,
            check=True,
        )
        diff_text = res.stdout
        # Limit to 200 KB
        if len(diff_text.encode("utf-8")) > 200 * 1024:
            diff_text = diff_text[: 200 * 1024]

        res_stat = subprocess.run(
            ["git", "-C", str(consumer_path), "diff", "--stat", f"{base_branch}...{branch}"],
            capture_output=True,
            text=True,
            check=True,
        )
        diffstat = res_stat.stdout
    except Exception:
        pass

    steps = [
        {"id": "S1", "name": "Detect contract drift", "type": "deterministic", "status": "done" if drift else "skipped"},
        {"id": "S2", "name": "Trace downstream candidates", "type": "deterministic", "status": "done" if candidates else "skipped"},
        {"id": "S3", "name": "Tracer subagent: impact map", "type": "ai", "status": "done" if impact else "skipped"},
        {"id": "S4", "name": "Transformer subagent: tolerant reader", "type": "ai", "status": "done" if branch else "skipped"},
        {"id": "S5", "name": "Deterministic container verification", "type": "deterministic", "status": "done" if verification else "skipped"},
        {"id": "S6", "name": "Verifier subagent: verdict", "type": "ai", "status": "done" if verdict else "skipped"},
        {"id": "S7", "name": "Human approval gate", "type": "human", "status": "done" if companion_pr_url else "skipped"},
        {"id": "S8", "name": "Draft companion PR", "type": "deterministic", "status": "done" if companion_pr_url else "skipped"},
        {"id": "S9", "name": "Publish run artifact", "type": "deterministic", "status": "done"},
    ]

    artifact_data: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "upstream_pr_url": upstream_pr_url,
        "companion_pr_url": companion_pr_url,
        "branch": branch,
        "drift": drift,
        "candidates": candidates,
        "impact": impact,
        "verification": verification,
        "verdict": verdict,
        "diff": diff_text,
        "diffstat": diffstat,
        "steps": steps,
        "bob_session_export": bob_export,
    }

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    target_file = out_path / f"{run_id}.json"
    target_file.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")
    return target_file
