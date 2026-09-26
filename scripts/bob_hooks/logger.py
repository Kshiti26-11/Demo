#!/usr/bin/env python3
"""SyncSnitch hook logger: appends one JSON line per IBM Bob hook event to bob_sessions/raw/<date>-<device>.jsonl.

Only metadata is logged (event, tool, key names) - never file contents or secrets.
"""
import datetime
import json
import re
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        event = {}
    if not isinstance(event, dict):
        event = {}
    now = datetime.datetime.now(datetime.timezone.utc)
    record = {
        "ts": now.isoformat(timespec="seconds"),
        "event": event.get("hook_event_name") or event.get("hookEventName") or event.get("event"),
        "tool": event.get("tool_name") or event.get("toolName") or event.get("tool"),
        "keys": sorted(event.keys())[:20],
    }
    device = re.sub(r"[^A-Za-z0-9_.-]", "-", socket.gethostname())[:40] or "device"
    out = ROOT / "bob_sessions" / "raw" / f"{now:%Y-%m-%d}-{device}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
