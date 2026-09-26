import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Sequence
import xml.etree.ElementTree as ET
import yaml

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from .runner import Runner


def resolve_ref(runner: Runner, repo: Path, ref: str) -> str:
    code, out = runner.run(["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"])
    if code == 0 and out.strip():
        return out.strip().splitlines()[0]
    code, out = runner.run(["git", "-C", str(repo), "rev-parse", "--verify", f"origin/{ref}^{{commit}}"])
    if code == 0 and out.strip():
        return out.strip().splitlines()[0]
    raise ValueError(f"Could not resolve git ref {ref} in {repo}")


def main(argv: Sequence[str] | None = None, runner: Runner | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if runner is None:
        runner = Runner()

    parser = argparse.ArgumentParser(prog="syncsnitch verify", description="Verify contract compatibility")
    parser.add_argument("--run-id", required=True, help="Run ID")
    parser.add_argument("--upstream", required=True, type=Path, help="Upstream repo directory")
    parser.add_argument("--base", required=True, help="Base git ref")
    parser.add_argument("--head", required=True, help="Head git ref")
    parser.add_argument("--consumer", required=True, type=Path, help="Consumer repo directory")
    parser.add_argument("--consumer-base", default="main", help="Consumer base ref")
    parser.add_argument("--runs-dir", default=Path(".syncsnitch/runs"), type=Path, help="Runs directory")
    parser.add_argument("--compose-file", default=Path("verify/docker-compose.yml"), type=Path, help="Compose file")
    parser.add_argument("--versions", default="v1,v2", help="Comma-separated versions to test")
    parser.add_argument("--no-containers", action="store_true", help="Skip container verification")

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code != 0 else 0

    run_id = args.run_id
    runs_dir = args.runs_dir.resolve()
    run_folder = runs_dir / run_id
    run_folder.mkdir(parents=True, exist_ok=True)

    upstream = args.upstream.resolve()
    consumer = args.consumer.resolve()

    try:
        base_sha = resolve_ref(runner, upstream, args.base)
        head_sha = resolve_ref(runner, upstream, args.head)
        consumer_sha = resolve_ref(runner, consumer, "HEAD")
        consumer_base_sha = resolve_ref(runner, consumer, args.consumer_base)
    except Exception as e:
        print(f"Error resolving git refs: {e}", file=sys.stderr)
        return 2

    wt_v1 = run_folder / "upstream-v1"
    wt_v2 = run_folder / "upstream-v2"
    results_dir = run_folder / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    worktrees_created = []
    checks: list[dict[str, Any]] = []

    try:
        # Create worktrees
        runner.run(["git", "-C", str(upstream), "worktree", "add", "--detach", str(wt_v1), base_sha])
        worktrees_created.append(wt_v1)
        runner.run(["git", "-C", str(upstream), "worktree", "add", "--detach", str(wt_v2), head_sha])
        worktrees_created.append(wt_v2)

        # Check V1: consumer unit tests
        code_v1, out_v1 = runner.run(["uv", "run", "pytest", "-q"], cwd=consumer)
        last_lines = [line.strip() for line in out_v1.strip().splitlines() if line.strip()][-15:]
        details_v1 = "\n".join(last_lines) if last_lines else "pytest completed"
        checks.append({
            "id": "V1",
            "name": "consumer unit tests",
            "status": "pass" if code_v1 == 0 else "fail",
            "details": details_v1,
        })

        # Check V2: v2 fixtures match the new contract
        v2_fixtures = list(consumer.glob("tests/fixtures/*v2*.json"))
        if not v2_fixtures:
            checks.append({
                "id": "V2",
                "name": "v2 fixtures match the new contract",
                "status": "fail",
                "details": "no v2 fixtures found",
            })
        else:
            v2_openapi_file = wt_v2 / "contracts" / "openapi.yaml"
            if not v2_openapi_file.exists():
                v2_openapi_file = Path("contracts/reference/v2/openapi.yaml")

            if not v2_openapi_file.exists():
                checks.append({
                    "id": "V2",
                    "name": "v2 fixtures match the new contract",
                    "status": "fail",
                    "details": "upstream v2 openapi.yaml not found",
                })
            else:
                try:
                    spec = yaml.safe_load(v2_openapi_file.read_text(encoding="utf-8"))
                    registry = Registry().with_resource("urn:spec", Resource.from_contents(spec, default_specification=DRAFT202012))
                    validator = Draft202012Validator({"$ref": "urn:spec#/components/schemas/Order"}, registry=registry)
                    for fix_path in v2_fixtures:
                        fix_data = json.loads(fix_path.read_text(encoding="utf-8"))
                        validator.validate(fix_data)
                    checks.append({
                        "id": "V2",
                        "name": "v2 fixtures match the new contract",
                        "status": "pass",
                        "details": f"{len(v2_fixtures)} v2 fixtures match schema",
                    })
                except Exception as err:
                    checks.append({
                        "id": "V2",
                        "name": "v2 fixtures match the new contract",
                        "status": "fail",
                        "details": f"fixture validation error: {err}",
                    })

        # Check V3 & V4: mock containers
        junit_data: dict[str, dict[str, Any]] = {}
        versions_to_test = [v.strip() for v in args.versions.split(",") if v.strip()]

        for ver in ("v1", "v2"):
            chk_id = "V3" if ver == "v1" else "V4"
            chk_name = "consumer vs upstream v1 (backward compatible)" if ver == "v1" else "consumer vs upstream v2 (new contract)"

            if args.no_containers or ver not in versions_to_test:
                checks.append({
                    "id": chk_id,
                    "name": chk_name,
                    "status": "skip",
                    "details": "skipped (--no-containers)",
                })
                continue

            wt = wt_v1 if ver == "v1" else wt_v2
            project_raw = f"ss-{run_id}-{ver}".lower()
            project = re.sub(r"[^a-z0-9-]", "", project_raw)

            compose_env = {
                "UPSTREAM_DIR": str(wt),
                "CONSUMER_DIR": str(consumer),
                "RESULTS_DIR": str(results_dir),
                "CONTRACT_VERSION": ver,
            }

            compose_file_str = str(args.compose_file)

            up_cmd = [
                "docker", "compose", "-f", compose_file_str, "-p", project,
                "up", "--build", "--abort-on-container-exit", "--exit-code-from", "billing-contract-tests",
            ]
            down_cmd = [
                "docker", "compose", "-f", compose_file_str, "-p", project,
                "down", "-v", "--remove-orphans",
            ]

            try:
                code_up, out_up = runner.run(up_cmd, env=compose_env)
            except Exception as err:
                code_up, out_up = 1, f"compose up error: {err}"
            finally:
                try:
                    runner.run(down_cmd, env=compose_env)
                except Exception:
                    pass

            # Parse junit xml
            junit_file = results_dir / f"junit-{ver}.xml"
            if not junit_file.exists():
                checks.append({
                    "id": chk_id,
                    "name": chk_name,
                    "status": "fail",
                    "details": f"junit-{ver}.xml not found (exit code {code_up})",
                })
            else:
                try:
                    tree = ET.parse(junit_file)
                    root = tree.getroot()
                    testcases = root.findall(".//testcase")
                    total_tests = len(testcases)
                    failures = []
                    passed_cases = set()

                    for tc in testcases:
                        tc_name = tc.get("name", "unknown")
                        tc_fail = tc.find("failure")
                        tc_err = tc.find("error")
                        if tc_fail is not None or tc_err is not None:
                            failures.append(tc_name)
                        else:
                            passed_cases.add(tc_name)

                    passed_count = total_tests - len(failures)
                    is_pass = (code_up == 0 and total_tests >= 1 and len(failures) == 0)

                    details = f"{passed_count}/{total_tests} passed"
                    if failures:
                        details += f" (failures: {', '.join(failures)})"

                    junit_data[ver] = {
                        "total": total_tests,
                        "passed": passed_count,
                        "failures": failures,
                        "passed_cases": passed_cases,
                    }

                    checks.append({
                        "id": chk_id,
                        "name": chk_name,
                        "status": "pass" if is_pass else "fail",
                        "details": details,
                    })
                except Exception as err:
                    checks.append({
                        "id": chk_id,
                        "name": chk_name,
                        "status": "fail",
                        "details": f"XML parse error: {err}",
                    })

        # Check V5: Prism contract examples
        if args.no_containers:
            checks.append({
                "id": "V5",
                "name": "Prism contract examples",
                "status": "skip",
                "details": "skipped (--no-containers)",
            })
        else:
            v1_cases = junit_data.get("v1", {}).get("passed_cases", set())
            v2_cases = junit_data.get("v2", {}).get("passed_cases", set())
            prism_case = "test_rest_contract_examples_parse"
            v5_pass = (prism_case in v1_cases and prism_case in v2_cases)
            details_v5 = f"{prism_case} passed against v1 and v2" if v5_pass else f"{prism_case} not passed in both runs"
            checks.append({
                "id": "V5",
                "name": "Prism contract examples",
                "status": "pass" if v5_pass else "fail",
                "details": details_v5,
            })

        # Check V6: diff scope
        code_diff, out_diff = runner.run(["git", "-C", str(consumer), "diff", "--name-only", f"{consumer_base_sha}...HEAD"])
        changed_paths = [line.strip().replace("\\", "/") for line in out_diff.strip().splitlines() if line.strip()]

        if not changed_paths:
            checks.append({
                "id": "V6",
                "name": "diff scope",
                "status": "pass",
                "details": "no changes",
            })
        else:
            code_del, out_del = runner.run(["git", "-C", str(consumer), "diff", "--name-only", "--diff-filter=D", f"{consumer_base_sha}...HEAD"])
            deleted_paths = [line.strip().replace("\\", "/") for line in out_del.strip().splitlines() if line.strip()]
            del_tests = [p for p in deleted_paths if p.startswith("tests/")]

            allowed_prefixes = ("billing/", "contracts/upstream/", "tests/", "scripts/")
            allowed_exact = ("README.md", ".syncsnitch.json")

            disallowed = []
            for p in changed_paths:
                if not (any(p.startswith(pref) for pref in allowed_prefixes) or p in allowed_exact):
                    disallowed.append(p)

            if del_tests:
                checks.append({
                    "id": "V6",
                    "name": "diff scope",
                    "status": "fail",
                    "details": f"tests deleted: {', '.join(del_tests)}",
                })
            elif disallowed:
                checks.append({
                    "id": "V6",
                    "name": "diff scope",
                    "status": "fail",
                    "details": f"paths outside scope: {', '.join(disallowed)}",
                })
            else:
                checks.append({
                    "id": "V6",
                    "name": "diff scope",
                    "status": "pass",
                    "details": f"{len(changed_paths)} files changed within scope",
                })

    finally:
        # Cleanup worktrees
        for wt in worktrees_created:
            runner.run(["git", "-C", str(upstream), "worktree", "remove", "--force", str(wt)])

    # Output verification.json and VERIFICATION.md
    passed_count = sum(1 for c in checks if c["status"] == "pass")
    failed_count = sum(1 for c in checks if c["status"] == "fail")
    skipped_count = sum(1 for c in checks if c["status"] == "skip")
    verdict = "green" if failed_count == 0 else "red"

    verification_data = {
        "run_id": run_id,
        "consumer_sha": consumer_sha,
        "upstream": {
            "base_sha": base_sha,
            "head_sha": head_sha,
        },
        "checks": checks,
        "summary": {
            "passed": passed_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "verdict": verdict,
        },
    }

    (run_folder / "verification.json").write_text(json.dumps(verification_data, indent=2), encoding="utf-8")

    md_lines = [
        f"# SyncSnitch Verification — {run_id}",
        "",
        f"**Verdict:** {('✅ GREEN' if verdict == 'green' else '❌ RED')}",
        "",
        "| Check | Name | Result | Details |",
        "|---|---|---|---|",
    ]
    for c in checks:
        icon = "✅ pass" if c["status"] == "pass" else ("❌ fail" if c["status"] == "fail" else "⏭️ skip")
        details_one_line = c["details"].replace("\n", " ")
        md_lines.append(f"| `{c['id']}` | {c['name']} | {icon} | {details_one_line} |")

    md_text = "\n".join(md_lines) + "\n"
    (run_folder / "VERIFICATION.md").write_text(md_text, encoding="utf-8")

    print(md_text)

    return 0 if verdict == "green" else 1


if __name__ == "__main__":
    sys.exit(main())
