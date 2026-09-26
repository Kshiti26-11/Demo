"""Report package: render PR body and CI comment from run artefacts."""
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _load_json_if_exists(path: Path) -> dict | None:
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _build_context(run_dir: Path, upstream_pr_url: str = "") -> dict:
    drift = _load_json_if_exists(run_dir / "drift.json") or {}
    candidates = _load_json_if_exists(run_dir / "candidates.json")
    impact = _load_json_if_exists(run_dir / "impact.json")
    verification = _load_json_if_exists(run_dir / "verification.json")
    verdict = _load_json_if_exists(run_dir / "verdict.json")

    changes = drift.get("changes", [])
    breaking_changes = [c for c in changes if c.get("breaking")]

    by_surface = drift.get("summary", {}).get("by_surface", {})
    breaking_by_surface = {
        "rest": sum(1 for c in breaking_changes if c["surface"] == "rest"),
        "grpc": sum(1 for c in breaking_changes if c["surface"] == "grpc"),
        "db": sum(1 for c in breaking_changes if c["surface"] == "db"),
    }

    return {
        "run_id": drift.get("run_id", ""),
        "upstream": drift.get("upstream", {}),
        "summary": drift.get("summary", {"total": 0, "breaking": 0, "by_surface": {}}),
        "changes": changes,
        "breaking_changes": breaking_changes,
        "breaking_by_surface": breaking_by_surface,
        "candidates": candidates,
        "impact": impact,
        "verification": verification,
        "verdict": verdict,
        "upstream_pr_url": upstream_pr_url,
    }


def render(run_dir: str | Path, fmt: str = "pr", upstream_pr_url: str = "") -> str:
    """
    Render a report for the given run directory.

    fmt: "pr" for PR body, "comment" for CI comment.
    Returns the rendered markdown string.
    """
    run_dir = Path(run_dir)
    ctx = _build_context(run_dir, upstream_pr_url)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
    )

    template_name = "pr_body.md.j2" if fmt == "pr" else "comment.md.j2"
    tmpl = env.get_template(template_name)
    return tmpl.render(**ctx)
