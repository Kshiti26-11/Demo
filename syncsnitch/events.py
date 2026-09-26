"""Run event log: <runs_dir>/<run_id>/events.jsonl, one JSON object per line.

Written by the deterministic CLI steps, by `syncsnitch log` (the IBM Bob agents call it at the start and end of
S3/S4/S6) and by the demo website; the website's live run page streams it.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

AGENTS = ("engine", "tracer", "transformer", "verifier", "human", "bob", "site")
LEVELS = ("info", "ok", "warn", "error")
_LOCK = threading.Lock()


def emit(runs_dir: str | Path, run_id: str, step: str, agent: str, msg: str, level: str = "info") -> dict:
    """Append one event and return it."""
    event = {
        "ts": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
        "step": step,
        "agent": agent if agent in AGENTS else "engine",
        "level": level if level in LEVELS else "info",
        "msg": msg,
    }
    run_dir = Path(runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with _LOCK, (run_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")
    return event


def read(runs_dir: str | Path, run_id: str) -> list[dict]:
    path = Path(runs_dir) / run_id / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events
