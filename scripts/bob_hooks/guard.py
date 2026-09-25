#!/usr/bin/env python3
"""SyncSnitch PreToolUse guard for IBM Bob hooks (reads one JSON event on stdin).

While a SyncSnitch run is active (.syncsnitch/ACTIVE exists in the main repo), block file writes
that target the upstream repo (orders-service) or look like secrets.
Exit 0 = allow. Exit 2 = block (JSON decision on stdout, reason on stderr).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = ROOT / ".syncsnitch" / "ACTIVE"
PATH_KEYS = {"path", "file_path", "filepath", "target_file", "file", "target"}
SECRET_MARKERS = (".env", "secret", "id_rsa", ".pem")


def paths_in(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and key.lower() in PATH_KEYS:
                yield value
            else:
                yield from paths_in(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from paths_in(value)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not ACTIVE.exists():
        return 0
    for path in paths_in(event):
        norm = path.replace("\\", "/").lower()
        name = norm.rsplit("/", 1)[-1]
        if "orders-service" in norm or any(marker in name for marker in SECRET_MARKERS):
            reason = f"SyncSnitch guard: writing {path} is blocked during a run (upstream repo or secret)"
            print(json.dumps({"decision": "block", "reason": reason}))
            print(reason, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
