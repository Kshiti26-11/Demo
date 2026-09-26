import argparse
from pathlib import Path
import sys
from typing import Sequence

from .detect import run_detect
from .gitutil import new_run_id
from .report import render
from .runs import write_run_artifact
from .trace import run_trace


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(prog="syncsnitch", description="Autonomous contract-drift agent")
    subparsers = parser.add_subparsers(dest="command")

    # detect
    p_detect = subparsers.add_parser("detect", help="Detect contract drift upstream")
    p_detect.add_argument("--upstream", required=True, type=Path, help="Upstream repo directory")
    p_detect.add_argument("--base", required=True, help="Base git ref")
    p_detect.add_argument("--head", required=True, help="Head git ref")
    p_detect.add_argument("--run-id", default=None, help="Run ID")
    p_detect.add_argument("--runs-dir", default=Path(".syncsnitch/runs"), type=Path, help="Runs directory")

    # trace
    p_trace = subparsers.add_parser("trace", help="Trace candidates downstream")
    p_trace.add_argument("--run-id", required=True, help="Run ID")
    p_trace.add_argument("--consumer", required=True, type=Path, help="Consumer repo directory")
    p_trace.add_argument("--runs-dir", default=Path(".syncsnitch/runs"), type=Path, help="Runs directory")

    # report
    p_report = subparsers.add_parser("report", help="Generate PR body or CI comment")
    p_report.add_argument("--run-id", required=True, help="Run ID")
    p_report.add_argument("--format", required=True, choices=["pr", "comment"], help="Output format")
    p_report.add_argument("--upstream-pr-url", default=None, help="Upstream PR URL")
    p_report.add_argument("--runs-dir", default=Path(".syncsnitch/runs"), type=Path, help="Runs directory")

    # run-artifact
    p_artifact = subparsers.add_parser("run-artifact", help="Write JSON run artifact for the demo site")
    p_artifact.add_argument("--run-id", required=True, help="Run ID")
    p_artifact.add_argument("--consumer", required=True, type=Path, help="Consumer repo directory")
    p_artifact.add_argument("--branch", required=True, help="Consumer branch name")
    p_artifact.add_argument("--base-branch", default="main", help="Consumer base branch")
    p_artifact.add_argument("--upstream-pr-url", default=None, help="Upstream PR URL")
    p_artifact.add_argument("--companion-pr-url", default=None, help="Companion PR URL")
    p_artifact.add_argument("--bob-export", default=None, help="Path to Bob session export markdown")
    p_artifact.add_argument("--runs-dir", default=Path(".syncsnitch/runs"), type=Path, help="Runs directory")
    p_artifact.add_argument("--out-dir", default=Path("web/runs"), type=Path, help="Output directory")

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify contract compatibility", add_help=False)

    args, remaining = parser.parse_known_args(argv)

    if args.command == "detect":
        rid = args.run_id or new_run_id()
        drift = run_detect(args.upstream, args.base, args.head, rid, args.runs_dir)
        print(f"RUN_ID={rid}")
        for c in drift.get("changes", []):
            if c.get("breaking"):
                print(f"BREAKING: {c['surface']} {c['location']} ({c['kind']}) old={c.get('old')}")
        return 0

    elif args.command == "trace":
        candidates = run_trace(args.run_id, args.consumer, args.runs_dir)
        file_counts: dict[str, int] = {}
        for h in candidates.get("hits", []):
            f = h["file"]
            file_counts[f] = file_counts.get(f, 0) + 1
        print(f"Trace complete for run {args.run_id}: {len(candidates.get('hits', []))} hits across {len(file_counts)} files")
        for f, cnt in sorted(file_counts.items()):
            print(f"  {f}: {cnt} hits")
        return 0

    elif args.command == "report":
        run_folder = args.runs_dir / args.run_id
        text = render(run_folder, args.format, args.upstream_pr_url)
        print(text)
        return 0

    elif args.command == "run-artifact":
        out = write_run_artifact(
            run_id=args.run_id,
            runs_dir=args.runs_dir,
            consumer=args.consumer,
            branch=args.branch,
            base_branch=args.base_branch,
            upstream_pr_url=args.upstream_pr_url,
            companion_pr_url=args.companion_pr_url,
            bob_export=args.bob_export,
            out_dir=args.out_dir,
        )
        print(str(out))
        return 0

    elif args.command == "verify":
        try:
            from .verify.cli import main as verify_main
            return verify_main(remaining)
        except ImportError:
            print("syncsnitch verify is not built yet (Person 4 builds syncsnitch/verify/)")
            return 2

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
