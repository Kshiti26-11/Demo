import json
from pathlib import Path
import re
from typing import Any
import jinja2


def _regex_replace(s: str, find: str, replace: str) -> str:
    return re.sub(find, replace, s)


def render(run_dir: Path, fmt: str, upstream_pr_url: str | None = None) -> str:
    run_dir = Path(run_dir)

    def load_json(name: str) -> dict[str, Any] | None:
        p = run_dir / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    drift = load_json("drift.json")
    if not drift:
        raise FileNotFoundError(f"drift.json not found in {run_dir}")

    candidates = load_json("candidates.json")
    impact = load_json("impact.json")
    verification = load_json("verification.json")
    verdict = load_json("verdict.json")

    run_id = drift.get("run_id", run_dir.name)

    context = {
        "run_id": run_id,
        "upstream_pr_url": upstream_pr_url,
        "drift": drift,
        "candidates": candidates,
        "impact": impact,
        "verification": verification,
        "verdict": verdict,
    }

    templates_dir = Path(__file__).parent / "templates"
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_dir), autoescape=False)
    env.filters["regex_replace"] = _regex_replace

    if fmt == "pr":
        tmpl = env.get_template("pr_body.md.j2")
        out_filename = "pr_body.md"
    elif fmt == "comment":
        tmpl = env.get_template("comment.md.j2")
        out_filename = "comment.md"
    else:
        raise ValueError(f"Unknown format: {fmt}")

    output_text = tmpl.render(context)
    (run_dir / out_filename).write_text(output_text, encoding="utf-8")
    return output_text
