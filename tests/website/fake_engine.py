#!/usr/bin/env python3
"""Stand-in for the `syncsnitch` CLI steps the runner calls (verify, report, run-artifact), without containers,
consumer venvs or pytest-in-pytest. The real CLI is covered by tests/engine.

FAKE_VERIFY=pass|fail-once|fail (default pass): V1 fails on every run (fail), or on the first run only (fail-once).
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd")
    p.add_argument("--run-id", required=True)
    p.add_argument("--runs-dir", required=True)
    p.add_argument("--no-containers", action="store_true")
    p.add_argument("--out-dir")
    p.add_argument("--companion-pr-url")
    args, _ = p.parse_known_args()
    import os

    run_dir = Path(args.runs_dir) / args.run_id
    if args.cmd == "verify":
        counter = run_dir / "fake-verify-count"
        n = int(counter.read_text()) + 1 if counter.exists() else 1
        counter.write_text(str(n))
        mode = os.environ.get("FAKE_VERIFY", "pass")
        v1 = "fail" if mode == "fail" or (mode == "fail-once" and n == 1) else "pass"
        skip = "skip" if args.no_containers else "pass"
        checks = [{"id": "V1", "name": "consumer unit tests", "status": v1, "details": f"run {n}"},
                  {"id": "V2", "name": "v2 fixtures", "status": "pass", "details": "2 v2 fixtures match schema"},
                  {"id": "V3", "name": "vs v1", "status": skip, "details": "skipped (--no-containers)"},
                  {"id": "V4", "name": "vs v2", "status": skip, "details": "skipped (--no-containers)"},
                  {"id": "V5", "name": "Prism", "status": skip, "details": "skipped (--no-containers)"},
                  {"id": "V6", "name": "diff scope", "status": "pass", "details": "1 files changed within scope"}]
        (run_dir / "verification.json").write_text(json.dumps({"run_id": args.run_id, "checks": checks, "summary": {}}))
        print(f"verify run {n}: V1 {v1}")
        return 0
    if args.cmd == "report":
        (run_dir / "pr_body.md").write_text("## SyncSnitch companion PR\n")
        return 0
    if args.cmd == "run-artifact":
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{args.run_id}.json").write_text(json.dumps({
            "run_id": args.run_id, "created_at": "2099-01-01T00:00:00+00:00",
            "companion_pr_url": args.companion_pr_url, "diff": "diff --git a/app.py b/app.py\n"}))
        print(f"wrote {out / (args.run_id + '.json')}")
        return 0
    print(f"unknown command {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
