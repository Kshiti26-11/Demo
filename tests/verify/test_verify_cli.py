import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
import pytest
from syncsnitch.verify.cli import main
from syncsnitch.verify.runner import Runner


class FakeRunner(Runner):
    def __init__(self, compose_failures: dict[str, int] | None = None, raise_on_compose: bool = False):
        self.compose_failures = compose_failures or {}
        self.raise_on_compose = raise_on_compose
        self.executed_commands: list[list[str]] = []

    def run(self, args: list[str], cwd=None, env=None, timeout=900) -> tuple[int, str]:
        self.executed_commands.append(args)
        cmd_str = " ".join(args)

        # Real git calls for worktree, rev-parse, diff
        if args and args[0] == "git":
            return super().run(args, cwd=cwd, env=env, timeout=timeout)

        # Pytest in consumer
        if "pytest" in cmd_str:
            return 0, "5 passed in 0.10s\n"

        # Docker compose up
        if "compose" in args and "up" in args:
            if self.raise_on_compose:
                raise RuntimeError("Simulated docker failure")

            ver = env.get("CONTRACT_VERSION", "v1") if env else "v1"
            results_dir = Path(env["RESULTS_DIR"]) if env and "RESULTS_DIR" in env else Path(".")
            results_dir.mkdir(parents=True, exist_ok=True)
            junit_path = results_dir / f"junit-{ver}.xml"

            fail_count = self.compose_failures.get(ver, 0)
            if fail_count == 0:
                # 5 passed
                junit_path.write_text('''<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="5" errors="0" failures="0" skipped="0">
    <testcase classname="tests.integration.test_contract" name="test_invoices_paid" />
    <testcase classname="tests.integration.test_contract" name="test_invoices_unpaid" />
    <testcase classname="tests.integration.test_contract" name="test_payments_status" />
    <testcase classname="tests.integration.test_contract" name="test_revenue_report" />
    <testcase classname="tests.integration.test_contract" name="test_rest_contract_examples_parse" />
  </testsuite>
</testsuites>
''', encoding="utf-8")
                return 0, "containers passed"
            else:
                # 5 failed
                junit_path.write_text('''<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="5" errors="0" failures="5" skipped="0">
    <testcase classname="tests.integration.test_contract" name="test_invoices_paid"><failure message="500">error</failure></testcase>
    <testcase classname="tests.integration.test_contract" name="test_invoices_unpaid"><failure message="500">error</failure></testcase>
    <testcase classname="tests.integration.test_contract" name="test_payments_status"><failure message="amount 0">error</failure></testcase>
    <testcase classname="tests.integration.test_contract" name="test_revenue_report"><failure message="sql">error</failure></testcase>
    <testcase classname="tests.integration.test_contract" name="test_rest_contract_examples_parse"><failure message="failed">error</failure></testcase>
  </testsuite>
</testsuites>
''', encoding="utf-8")
                return 1, "containers failed"

        # Docker compose down
        if "compose" in args and "down" in args:
            return 0, "down ok"

        return super().run(args, cwd=cwd, env=env, timeout=timeout)


@pytest.fixture
def repos(tmp_path):
    # Upstream repo
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=upstream, check=True, capture_output=True)

    c_dir = upstream / "contracts"
    c_dir.mkdir()
    shutil.copy("contracts/reference/v1/openapi.yaml", c_dir / "openapi.yaml")

    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-m", "v1 openapi"],
        cwd=upstream,
        check=True,
        capture_output=True,
    )

    subprocess.run(["git", "checkout", "-b", "feat/v2"], cwd=upstream, check=True, capture_output=True)
    shutil.copy("contracts/reference/v2/openapi.yaml", c_dir / "openapi.yaml")

    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-m", "v2 openapi"],
        cwd=upstream,
        check=True,
        capture_output=True,
    )

    # Consumer repo
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=consumer, check=True, capture_output=True)

    fix_dir = consumer / "tests" / "fixtures"
    fix_dir.mkdir(parents=True)
    # Copy v2 paid example
    v2_paid = {
        "order_id": "o-1001",
        "customer": {"customer_id": "c-1001", "display_name": "Ada Lovelace"},
        "total": {"amount_minor": 1999, "currency": "USD"},
        "status": "PAID",
        "created_at": "2026-09-01T10:00:00Z"
    }
    (fix_dir / "order_v2_paid.json").write_text(json.dumps(v2_paid), encoding="utf-8")
    (consumer / "billing").mkdir()
    (consumer / "billing" / "app.py").write_text("# billing app", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=consumer, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-m", "consumer main"],
        cwd=consumer,
        check=True,
        capture_output=True,
    )

    return upstream, consumer


def test_verify_all_pass(repos, tmp_path):
    upstream, consumer = repos
    runs_dir = tmp_path / "runs"
    runner = FakeRunner()

    rc = main([
        "--run-id", "pass-1",
        "--upstream", str(upstream),
        "--base", "main",
        "--head", "feat/v2",
        "--consumer", str(consumer),
        "--runs-dir", str(runs_dir),
    ], runner=runner)

    assert rc == 0
    res_file = runs_dir / "pass-1" / "verification.json"
    assert res_file.exists()
    data = json.loads(res_file.read_text(encoding="utf-8"))
    assert data["summary"]["verdict"] == "green"
    assert data["summary"]["passed"] == 6


def test_verify_v2_failure(repos, tmp_path):
    upstream, consumer = repos
    runs_dir = tmp_path / "runs"
    # v2 compose has failures
    runner = FakeRunner(compose_failures={"v2": 5})

    rc = main([
        "--run-id", "fail-v2",
        "--upstream", str(upstream),
        "--base", "main",
        "--head", "feat/v2",
        "--consumer", str(consumer),
        "--runs-dir", str(runs_dir),
    ], runner=runner)

    assert rc == 1
    data = json.loads((runs_dir / "fail-v2" / "verification.json").read_text(encoding="utf-8"))
    assert data["summary"]["verdict"] == "red"
    check_map = {c["id"]: c for c in data["checks"]}
    assert check_map["V4"]["status"] == "fail"
    assert check_map["V5"]["status"] == "fail"


def test_verify_no_v2_fixture(repos, tmp_path):
    upstream, consumer = repos
    runs_dir = tmp_path / "runs"
    # Remove v2 fixtures
    for f in (consumer / "tests" / "fixtures").glob("*"):
        f.unlink()

    runner = FakeRunner()
    rc = main([
        "--run-id", "no-fix",
        "--upstream", str(upstream),
        "--base", "main",
        "--head", "feat/v2",
        "--consumer", str(consumer),
        "--runs-dir", str(runs_dir),
    ], runner=runner)

    assert rc == 1
    data = json.loads((runs_dir / "no-fix" / "verification.json").read_text(encoding="utf-8"))
    check_map = {c["id"]: c for c in data["checks"]}
    assert check_map["V2"]["status"] == "fail"


def test_verify_no_containers(repos, tmp_path):
    upstream, consumer = repos
    runs_dir = tmp_path / "runs"
    runner = FakeRunner()

    rc = main([
        "--run-id", "no-cnt",
        "--upstream", str(upstream),
        "--base", "main",
        "--head", "feat/v2",
        "--consumer", str(consumer),
        "--runs-dir", str(runs_dir),
        "--no-containers",
    ], runner=runner)

    assert rc == 0
    data = json.loads((runs_dir / "no-cnt" / "verification.json").read_text(encoding="utf-8"))
    check_map = {c["id"]: c for c in data["checks"]}
    assert check_map["V3"]["status"] == "skip"
    assert check_map["V4"]["status"] == "skip"
    assert check_map["V5"]["status"] == "skip"


def test_verify_worktrees_cleanup_on_error(repos, tmp_path):
    upstream, consumer = repos
    runs_dir = tmp_path / "runs"
    runner = FakeRunner(raise_on_compose=True)

    rc = main([
        "--run-id", "err-clean",
        "--upstream", str(upstream),
        "--base", "main",
        "--head", "feat/v2",
        "--consumer", str(consumer),
        "--runs-dir", str(runs_dir),
    ], runner=runner)

    # Worktrees should be removed
    assert not (runs_dir / "err-clean" / "upstream-v1").exists()
    assert not (runs_dir / "err-clean" / "upstream-v2").exists()


def test_verify_v6_fails_when_an_existing_fixture_is_edited(repos, tmp_path):
    """Editing the old examples (instead of adding new ones) can hide a broken v1 path: V6 must fail."""
    upstream, consumer = repos
    git = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com"]
    subprocess.run(["git", "checkout", "-q", "-b", "syncsnitch/x"], cwd=consumer, check=True)
    fixture = consumer / "tests" / "fixtures" / "order_v2_paid.json"
    fixture.write_text(fixture.read_text(encoding="utf-8").replace("1999", "2000"), encoding="utf-8")
    (consumer / "tests" / "fixtures" / "order_v2_unpaid.json").write_text("{}", encoding="utf-8")  # adding is fine
    subprocess.run([*git, "commit", "-qam", "edit the old fixture"], cwd=consumer, check=True)

    main(["--run-id", "v6-fix", "--upstream", str(upstream), "--base", "main", "--head", "feat/v2",
          "--consumer", str(consumer), "--consumer-base", "main", "--runs-dir", str(tmp_path / "runs"),
          "--no-containers"], runner=FakeRunner())
    data = json.loads((tmp_path / "runs" / "v6-fix" / "verification.json").read_text(encoding="utf-8"))
    v6 = {c["id"]: c for c in data["checks"]}["V6"]
    assert v6["status"] == "fail" and "existing fixtures edited" in v6["details"]
    assert "tests/fixtures/order_v2_paid.json" in v6["details"] and "order_v2_unpaid" not in v6["details"]
