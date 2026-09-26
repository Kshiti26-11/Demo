"""Report package: render the companion-PR body and the upstream CI comment from run artefacts."""
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_OUTPUT = {"pr": ("pr_body.md.j2", "pr_body.md"), "comment": ("comment.md.j2", "comment.md")}
ICONS = {"pass": "✅", "fail": "❌", "skip": "⏭️"}


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _context(run_dir: Path, upstream_pr_url: str | None) -> dict:
    drift = _load(run_dir / "drift.json") or {}
    changes = drift.get("changes", [])
    breaking = [c for c in changes if c.get("breaking")]
    candidates = _load(run_dir / "candidates.json")
    hits = (candidates or {}).get("hits", [])
    files: dict[str, set[str]] = {}
    for h in hits:
        files.setdefault(h["file"], set()).update(h.get("endpoints", []))
    return {
        "run_id": drift.get("run_id", run_dir.name),
        "upstream": drift.get("upstream", {}),
        "upstream_pr_url": upstream_pr_url or "",
        "summary": drift.get("summary", {"total": 0, "breaking": 0, "by_surface": {}}),
        "breaking_by_surface": {s: sum(1 for c in breaking if c["surface"] == s) for s in ("rest", "grpc", "db")},
        "changes": changes,
        "breaking_changes": breaking,
        "candidates": candidates,
        "affected_files": [{"file": f, "endpoints": sorted(eps)} for f, eps in sorted(files.items())],
        "impact": _load(run_dir / "impact.json"),
        "verification": _load(run_dir / "verification.json"),
        "verdict": _load(run_dir / "verdict.json"),
        "icons": ICONS,
    }


def render(run_dir: str | Path, fmt: str = "pr", upstream_pr_url: str | None = None) -> str:
    """Render fmt "pr" (pr_body.md) or "comment" (comment.md), write it into run_dir and return the text."""
    if fmt not in _OUTPUT:
        raise ValueError(f"unknown format {fmt!r} (use 'pr' or 'comment')")
    run_dir = Path(run_dir)
    template_name, out_name = _OUTPUT[fmt]
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    text = env.get_template(template_name).render(**_context(run_dir, upstream_pr_url))
    (run_dir / out_name).write_text(text, encoding="utf-8")
    return text
