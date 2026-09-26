#!/usr/bin/env python3
"""Stand-in for IBM Bob Shell in the tests: speaks `bob run --format stream-json` (the event shapes Bob Shell 2.0.5
emits) and does each SyncSnitch agent's job deterministically, so the runner can be tested without Bobcoins.

Knobs (environment): FAKE_BOB_FAIL=<mode> fails that session; FAKE_BOB_TRANSFORMER=noop makes no change;
FAKE_BOB_FIX=fail|noop fails / changes nothing in the Transformer's fix round;
FAKE_BOB_UNCOMMITTED=1 leaves the edit uncommitted; FAKE_BOB_VERDICT=green always says green;
FAKE_BOB_COST=<bobcoins> per session; FAKE_BOB_RECORD=<file> appends every call as JSON.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def out(event: dict) -> None:
    event.setdefault("timestamp", "2026-09-26T00:00:00.000Z")
    print(json.dumps(event), flush=True)


def tool(name: str, params: dict, n: int) -> None:
    out({"type": "tool_use", "tool_name": name, "tool_id": f"t{n}", "parameters": params})
    out({"type": "tool_result", "tool_id": f"t{n}", "status": "success", "output": "ok"})


def main() -> int:
    args = sys.argv[1:]
    assert args[0] == "run", args
    opts, prompt, i = {}, "", 1
    while i < len(args):
        if args[i] == "--":
            prompt = " ".join(args[i + 1:])
            break
        if args[i] in ("--trust", "--disable-mcp", "--disable-subagents"):
            opts[args[i]] = True
            i += 1
            continue
        opts[args[i]] = args[i + 1]
        i += 2
    mode, ws = opts["--mode"], Path(opts["--workspace"])
    if os.environ.get("FAKE_BOB_RECORD"):
        with open(os.environ["FAKE_BOB_RECORD"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"mode": mode, "opts": opts, "prompt": prompt,
                                 "has_key": bool(os.environ.get("BOB_API_KEY"))}) + "\n")
    out({"type": "message", "role": "user", "content": prompt})
    fix_round = "fix round" in prompt
    if os.environ.get("FAKE_BOB_FAIL") == mode or (fix_round and os.environ.get("FAKE_BOB_FIX") == "fail"):
        out({"type": "error", "severity": "error", "message": "Bob API key is invalid"})
        print("Error: Bob API key is invalid", file=sys.stderr)
        return 1
    out({"type": "message", "role": "assistant", "isReasoning": True, "content": "thinking about it"})
    out({"type": "message", "role": "assistant", "content": "Reading the **run** files"})
    out({"type": "message", "role": "assistant", "content": " for this step.\n"})
    m = re.search(r"Read (\S+?)/(?:drift|impact|verification)\.json", prompt)
    run_rel = m.group(1) if m else ""
    run_dir = Path(run_rel) if Path(run_rel).is_absolute() else ws / run_rel
    run_id = run_dir.name

    if mode == "syncsnitch-tracer":
        tool("read_file", {"path": f"{run_rel}/drift.json"}, 1)
        impact = {"run_id": run_id, "mapping": [], "affected": [], "migration_notes": "Roll out v2 behind a flag.",
                  "endpoints": [{"endpoint": "POST /invoices/{order_id}", "surface": "rest", "failure": "loud",
                                 "why": "KeyError total_price"},
                                {"endpoint": "GET /payments/{order_id}/status", "surface": "grpc", "failure": "silent",
                                 "why": "total_price reads 0.0 from v2"}]}
        (run_dir / "impact.json").write_text(json.dumps(impact), encoding="utf-8")
        tool("write_to_file", {"path": f"{run_rel}/impact.json"}, 2)
    elif mode == "syncsnitch-transformer":
        cons = re.search(r"cd (\S+) && uv run pytest", prompt).group(1)
        cons_path = Path(cons) if Path(cons).is_absolute() else ws / cons
        skip = os.environ.get("FAKE_BOB_TRANSFORMER") == "noop" or (fix_round and os.environ.get("FAKE_BOB_FIX") == "noop")
        if not skip:
            app = cons_path / "app.py"
            app.write_text(app.read_text() + f"NOT_PAYABLE = {{'AWAITING_PAYMENT', 'PENDING'}}  # {len(prompt)}\n")
            tool("apply_diff", {"path": f"{cons}/app.py", "diff": "..."}, 3)
            tool("execute_command", {"command": f"cd {cons} && uv run pytest -q"}, 4)
            if os.environ.get("FAKE_BOB_UNCOMMITTED") != "1":
                subprocess.run(["git", "add", "-A", "."], cwd=cons_path, check=True)
                subprocess.run(["git", "commit", "-q", "-m", "fix(contract): tolerant reader"], cwd=cons_path,
                               check=True)
    elif mode == "syncsnitch-verifier":
        v = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
        failed = [c["id"] for c in v["checks"] if c["status"] == "fail"]
        green = not failed or os.environ.get("FAKE_BOB_VERDICT") == "green"
        verdict = {"run_id": run_id, "verdict": "green" if green else "red",
                   "reasons": ["all executed checks passed" if green else f"{', '.join(failed)} failed"],
                   "fix_instructions": [] if green else [f"cons/app.py: fix {x}" for x in failed]}
        (run_dir / "verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
        tool("write_to_file", {"path": f"{run_rel}/verdict.json"}, 5)
    out({"type": "message", "role": "assistant", "content": "Done."})
    out({"type": "result", "status": "success", "stats": {
        "task_id": f"task-{mode}", "duration_ms": 61000, "session_costs": float(os.environ.get("FAKE_BOB_COST", "0.4")),
        "max_cost": float(opts["--max-cost"]), "tool_calls": 3}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
