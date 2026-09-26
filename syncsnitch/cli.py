"""SyncSnitch CLI entry point."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cmd_detect(args: argparse.Namespace) -> int:
    from .gitutil import resolve_ref, new_run_id  # noqa: PLC0415
    from .detect import run_detect  # noqa: PLC0415

    run_id = args.run_id or new_run_id()
    repo = args.repo or str(Path.cwd())
    base_sha = resolve_ref(repo, args.base)
    head_sha = resolve_ref(repo, args.head)

    upstream = {
        "repo": repo,
        "base": args.base,
        "head": args.head,
        "base_sha": base_sha,
        "head_sha": head_sha,
    }

    runs_dir = args.runs_dir or "runs"
    drift = run_detect(upstream, base_sha, head_sha, run_id, runs_dir)

    print(json.dumps({"run_id": run_id, "summary": drift["summary"]}, indent=2))
    return 0


def _cmd_trace(args: argparse.Namespace) -> int:
    from .trace import run_trace  # noqa: PLC0415

    runs_dir = args.runs_dir or "runs"
    candidates = run_trace(args.run_id, args.consumer, runs_dir)
    print(json.dumps({"run_id": args.run_id, "summary": candidates["summary"]}, indent=2))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from .report import render  # noqa: PLC0415

    runs_dir = args.runs_dir or "runs"
    run_dir = Path(runs_dir) / args.run_id
    output = render(run_dir, fmt=args.fmt, upstream_pr_url=args.pr_url or "")

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output)
    return 0


def _cmd_run_artifact(args: argparse.Namespace) -> int:
    from .runs import write_run_artifact  # noqa: PLC0415

    runs_dir = args.runs_dir or "runs"
    web_runs_dir = args.web_runs_dir or "web/runs"

    artifact = write_run_artifact(
        run_id=args.run_id,
        runs_dir=runs_dir,
        web_runs_dir=web_runs_dir,
        upstream_pr_url=args.pr_url or "",
        companion_pr_url=args.companion_pr_url or "",
        branch=args.branch or "",
        diff=args.diff or "",
        diffstat=args.diffstat or "",
    )
    print(json.dumps({"run_id": args.run_id, "artifact": str(Path(web_runs_dir) / f"{args.run_id}.json")}, indent=2))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        from syncsnitch.verify import cli as verify_cli  # noqa: PLC0415
        return verify_cli.main_verify(args)
    except ImportError:
        print("syncsnitch verify is not built yet (Person 4 builds syncsnitch/verify/)")
        return 2


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="syncsnitch",
        description="Autonomous contract-drift detector built with IBM Bob.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # --- detect ---
    p_detect = sub.add_parser("detect", help="Detect contract drift between two refs")
    p_detect.add_argument("--repo", help="Path to the upstream git repository")
    p_detect.add_argument("--base", default="HEAD~1", help="Base ref (default: HEAD~1)")
    p_detect.add_argument("--head", default="HEAD", help="Head ref (default: HEAD)")
    p_detect.add_argument("--run-id", dest="run_id", help="Override run ID")
    p_detect.add_argument("--runs-dir", dest="runs_dir", default="runs", help="Runs output directory")

    # --- trace ---
    p_trace = sub.add_parser("trace", help="Trace downstream usages of breaking changes")
    p_trace.add_argument("run_id", help="Run ID from detect step")
    p_trace.add_argument("--consumer", required=True, help="Path to the consumer codebase")
    p_trace.add_argument("--runs-dir", dest="runs_dir", default="runs", help="Runs directory")

    # --- report ---
    p_report = sub.add_parser("report", help="Render a PR body or CI comment")
    p_report.add_argument("run_id", help="Run ID")
    p_report.add_argument("--fmt", choices=["pr", "comment"], default="pr", help="Output format")
    p_report.add_argument("--pr-url", dest="pr_url", help="Upstream PR URL")
    p_report.add_argument("--runs-dir", dest="runs_dir", default="runs", help="Runs directory")
    p_report.add_argument("--output", "-o", help="Write report to this file")

    # --- run-artifact ---
    p_artifact = sub.add_parser("run-artifact", help="Write run artifact JSON for demo website")
    p_artifact.add_argument("run_id", help="Run ID")
    p_artifact.add_argument("--runs-dir", dest="runs_dir", default="runs", help="Runs directory")
    p_artifact.add_argument("--web-runs-dir", dest="web_runs_dir", default="web/runs",
                             help="Output directory for web artifacts")
    p_artifact.add_argument("--pr-url", dest="pr_url", help="Upstream PR URL")
    p_artifact.add_argument("--companion-pr-url", dest="companion_pr_url", help="Companion PR URL")
    p_artifact.add_argument("--branch", help="Branch name")
    p_artifact.add_argument("--diff", help="Git diff text")
    p_artifact.add_argument("--diffstat", help="Git diffstat text")

    # --- verify ---
    p_verify = sub.add_parser("verify", help="Verify companion PR (Person 4)")
    p_verify.add_argument("run_id", nargs="?", help="Run ID")

    args = parser.parse_args()

    handlers = {
        "detect": _cmd_detect,
        "trace": _cmd_trace,
        "report": _cmd_report,
        "run-artifact": _cmd_run_artifact,
        "verify": _cmd_verify,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(0)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
