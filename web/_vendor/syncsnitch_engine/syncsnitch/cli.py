"""SyncSnitch CLI: the deterministic steps of the workflow (0 tokens at run time)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .events import AGENTS, LEVELS, emit

DEFAULT_RUNS_DIR = ".syncsnitch/runs"


def _verify_with_events(verify_main, argv: list[str]) -> int:
    """Run `syncsnitch verify` and record start/end events when a run id is given."""
    run_id = argv[argv.index("--run-id") + 1] if "--run-id" in argv[:-1] else None
    runs_dir = argv[argv.index("--runs-dir") + 1] if "--runs-dir" in argv[:-1] else DEFAULT_RUNS_DIR
    containers = "--no-containers" not in argv
    if run_id:
        emit(runs_dir, run_id, "S5", "verifier",
             "S5 verify: unit tests, v2 fixtures" + (", Docker mock containers vs v1 and v2" if containers else " (containers skipped)"))
    code = verify_main(argv)
    if run_id:
        vpath = Path(runs_dir) / run_id / "verification.json"
        if vpath.exists():
            import json  # noqa: PLC0415

            v = json.loads(vpath.read_text(encoding="utf-8"))
            s = v["summary"]
            emit(runs_dir, run_id, "S5", "verifier",
                 f"S5 verify: {s['passed']} passed, {s['failed']} failed, {s['skipped']} skipped -> {s['verdict'].upper()}",
                 "ok" if s["verdict"] == "green" else "warn")
        else:
            emit(runs_dir, run_id, "S5", "verifier", f"S5 verify stopped (exit {code})", "error")
    return code


def _cmd_detect(args: argparse.Namespace) -> int:
    from .detect import run_detect  # noqa: PLC0415

    emit(args.runs_dir, args.run_id, "S1", "engine", f"S1 detect: diffing contracts in {args.upstream} ({args.base} -> {args.head})")
    drift = run_detect(Path(args.upstream), args.base, args.head, args.run_id, Path(args.runs_dir))
    s = drift["summary"]
    bs = {x: sum(1 for c in drift["changes"] if c["breaking"] and c["surface"] == x) for x in ("rest", "grpc", "db")}
    emit(args.runs_dir, args.run_id, "S1", "engine",
         f"S1 detect: {s['breaking']} breaking of {s['total']} changes (REST {bs['rest']}, gRPC {bs['grpc']}, DB {bs['db']})", "ok")
    print(f"RUN_ID={args.run_id}")
    print(
        f"{s['breaking']} breaking of {s['total']} changes "
        f"(rest {s['by_surface']['rest']}, grpc {s['by_surface']['grpc']}, db {s['by_surface']['db']})"
    )
    for c in drift["changes"]:
        if c["breaking"]:
            print(f"  BREAKING {c['surface']:<4} {c['kind']:<20} {c['location']}  ({c['old']} -> {c['new']})")
    return 0


def _cmd_trace(args: argparse.Namespace) -> int:
    from .trace import run_trace  # noqa: PLC0415

    emit(args.runs_dir, args.run_id, "S2", "engine", f"S2 trace: scanning consumer {args.consumer}")
    candidates = run_trace(args.run_id, Path(args.consumer), Path(args.runs_dir))
    cs = candidates["summary"]
    emit(args.runs_dir, args.run_id, "S2", "engine",
         f"S2 trace: {cs['hits']} usages in {cs['files']} files -> {', '.join(cs['endpoints']) or 'no endpoints'}", "ok")
    by_file: dict[str, list[dict]] = {}
    for h in candidates["hits"]:
        by_file.setdefault(h["file"], []).append(h)
    for file, hits in by_file.items():
        endpoints = sorted({e for h in hits for e in h["endpoints"]})
        suffix = f"  -> {', '.join(endpoints)}" if endpoints else ""
        print(f"{file}: {len(hits)} hit(s){suffix}")
    s = candidates["summary"]
    print(f"{s['hits']} hits in {s['files']} files; endpoints: {', '.join(s['endpoints']) or 'none'}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from .report import render  # noqa: PLC0415

    print(render(Path(args.runs_dir) / args.run_id, args.format, args.upstream_pr_url), end="")
    emit(args.runs_dir, args.run_id, "S8", "engine", f"S8 report: {'pr_body.md' if args.format == 'pr' else 'comment.md'} rendered")
    return 0


def _cmd_run_artifact(args: argparse.Namespace) -> int:
    from .runs import write_run_artifact  # noqa: PLC0415

    path = write_run_artifact(
        run_id=args.run_id,
        runs_dir=Path(args.runs_dir),
        consumer=Path(args.consumer),
        branch=args.branch,
        base_branch=args.base_branch,
        upstream_pr_url=args.upstream_pr_url,
        companion_pr_url=args.companion_pr_url,
        bob_export=args.bob_export,
        out_dir=Path(args.out_dir),
    )
    emit(args.runs_dir, args.run_id, "S9", "engine", f"S9 run artifact written: {path}", "ok")
    print(path)
    return 0


def _cmd_log(args: argparse.Namespace) -> int:
    emit(args.runs_dir, args.run_id, args.step, args.agent, " ".join(args.message), args.level)
    return 0


def _parser() -> argparse.ArgumentParser:
    from .gitutil import new_run_id  # noqa: PLC0415

    parser = argparse.ArgumentParser(prog="syncsnitch", description="Autonomous, human-gated contract-drift agent.")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def common(p: argparse.ArgumentParser, run_id_required: bool) -> None:
        if run_id_required:
            p.add_argument("--run-id", required=True)
        else:
            p.add_argument("--run-id", default=new_run_id())
        p.add_argument("--runs-dir", default=DEFAULT_RUNS_DIR)

    p = sub.add_parser("detect", help="detect REST/gRPC/DB contract drift between two upstream refs")
    p.add_argument("--upstream", required=True, help="upstream checkout (a repo root or a monorepo sub-folder)")
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    common(p, run_id_required=False)
    p.set_defaults(func=_cmd_detect)

    p = sub.add_parser("trace", help="trace every consumer usage of the breaking changes")
    p.add_argument("--consumer", required=True)
    common(p, run_id_required=True)
    p.set_defaults(func=_cmd_trace)

    p = sub.add_parser("report", help="render the companion-PR body or the upstream CI comment")
    p.add_argument("--format", choices=["pr", "comment"], required=True)
    p.add_argument("--upstream-pr-url")
    common(p, run_id_required=True)
    p.set_defaults(func=_cmd_report)

    p = sub.add_parser("run-artifact", help="write web/runs/<run_id>.json for the demo website")
    p.add_argument("--consumer", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--base-branch", default="main")
    p.add_argument("--upstream-pr-url")
    p.add_argument("--companion-pr-url")
    p.add_argument("--bob-export")
    p.add_argument("--out-dir", default="web/runs")
    common(p, run_id_required=True)
    p.set_defaults(func=_cmd_run_artifact)

    p = sub.add_parser("log", help="record a progress event for the live run page (used by the IBM Bob agents)")
    p.add_argument("--step", required=True, help="S0-S9")
    p.add_argument("--agent", default="bob", choices=list(AGENTS))
    p.add_argument("--level", default="info", choices=list(LEVELS))
    p.add_argument("message", nargs="+")
    common(p, run_id_required=True)
    p.set_defaults(func=_cmd_log)

    sub.add_parser("verify", help="verify the consumer against upstream v1 and v2 (mock containers)", add_help=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "verify":
        try:
            from .verify.cli import main as verify_main  # noqa: PLC0415
        except ImportError:
            print("syncsnitch verify is not built yet (Person 4 builds syncsnitch/verify/)")
            return 2
        return _verify_with_events(verify_main, argv[1:])

    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
