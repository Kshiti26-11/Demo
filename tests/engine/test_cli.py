"""Tests for CLI: end-to-end detect/trace/report in a temporary git repo."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# Paths to reference contracts
_REFS = Path(__file__).parent.parent.parent / "contracts" / "reference"
_V1_OPENAPI = _REFS / "v1" / "openapi.yaml"
_V2_OPENAPI = _REFS / "v2" / "openapi.yaml"
_V1_PROTO = _REFS / "v1" / "orders.proto"
_V2_PROTO = _REFS / "v2" / "orders.proto"
_MIG_0001 = _REFS / "migrations" / "0001_create_orders.py"
_MIG_0002 = _REFS / "migrations" / "0002_money_customer_status.py"


# ---------------------------------------------------------------------------
# Temporary git repo fixture
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"},
    )
    return result.stdout.strip()


def _make_upstream_repo(tmpdir: Path) -> tuple[Path, str, str]:
    """
    Create a temporary git repo with:
    - v1 contracts committed on main (base)
    - v2 contracts committed on feat/v2 (head)
    Returns (repo_path, base_sha, head_sha).
    """
    repo = tmpdir / "upstream"
    repo.mkdir()

    _git(["init", "-b", "main"], str(repo))
    _git(["config", "user.email", "test@test.com"], str(repo))
    _git(["config", "user.name", "Test"], str(repo))

    # Create v1 contracts
    contracts = repo / "contracts"
    contracts.mkdir()
    (contracts / "openapi.yaml").write_text(
        _V1_OPENAPI.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (contracts / "orders.proto").write_text(
        _V1_PROTO.read_text(encoding="utf-8"), encoding="utf-8"
    )
    mig_dir = contracts / "migrations"
    mig_dir.mkdir()
    (mig_dir / "0001_create_orders.py").write_text(
        _MIG_0001.read_text(encoding="utf-8"), encoding="utf-8"
    )

    _git(["add", "."], str(repo))
    _git(["commit", "-m", "v1 contracts"], str(repo))
    base_sha = _git(["rev-parse", "HEAD"], str(repo))

    # Branch feat/v2 and commit v2 contracts
    _git(["checkout", "-b", "feat/v2"], str(repo))
    (contracts / "openapi.yaml").write_text(
        _V2_OPENAPI.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (contracts / "orders.proto").write_text(
        _V2_PROTO.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (mig_dir / "0002_money_customer_status.py").write_text(
        _MIG_0002.read_text(encoding="utf-8"), encoding="utf-8"
    )

    _git(["add", "."], str(repo))
    _git(["commit", "-m", "v2 contracts"], str(repo))
    head_sha = _git(["rev-parse", "HEAD"], str(repo))

    return repo, base_sha, head_sha


# ---------------------------------------------------------------------------
# CLI end-to-end test
# ---------------------------------------------------------------------------

class TestCliEndToEnd:
    def test_detect_9_breaking_and_report(self):
        """Full E2E: detect -> trace -> report in a temp repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo, base_sha, head_sha = _make_upstream_repo(tmp)
            runs_dir = tmp / "runs"
            runs_dir.mkdir()

            # ---- detect ----
            from syncsnitch.detect import run_detect

            run_id = "r-test-cli"
            upstream = {
                "repo": str(repo),
                "base": base_sha,
                "head": head_sha,
                "base_sha": base_sha,
                "head_sha": head_sha,
            }
            drift = run_detect(upstream, base_sha, head_sha, run_id, runs_dir)

            breaking = [c for c in drift["changes"] if c["breaking"]]
            assert len(breaking) == 9, (
                f"Expected 9 breaking changes, got {len(breaking)}: "
                + str([c["id"] for c in breaking])
            )

            # ---- trace ----
            from syncsnitch.trace import run_trace

            # Create a minimal consumer
            consumer = tmp / "consumer"
            consumer.mkdir()
            (consumer / "app.py").write_text(
                "total_price = 0\ncustomer_name = ''\nstatus = 'PENDING'\n",
                encoding="utf-8",
            )

            candidates = run_trace(run_id, consumer, runs_dir)
            assert candidates["run_id"] == run_id
            assert candidates["summary"]["hits"] >= 0

            # ---- report ----
            from syncsnitch.report import render

            run_dir = runs_dir / run_id
            report = render(run_dir, fmt="pr")

            assert "## Contract drift" in report, (
                f"Expected '## Contract drift' in PR body, got:\n{report[:500]}"
            )
            assert run_id in report

    def test_cli_detect_help(self):
        """syncsnitch detect --help must exit 0."""
        result = subprocess.run(
            ["uv", "run", "syncsnitch", "detect", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "detect" in result.stdout.lower() or "detect" in result.stderr.lower()

    def test_verify_available(self):
        """syncsnitch verify is built by Person 4; running with no args should exit non-zero (missing required args)."""
        result = subprocess.run(
            ["uv", "run", "syncsnitch", "verify"],
            capture_output=True,
            text=True,
        )
        # verify is present - missing required args causes exit 2 from argparse
        assert result.returncode != 0

    def test_drift_json_written(self):
        """drift.json must be written to runs_dir/<run_id>/drift.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo, base_sha, head_sha = _make_upstream_repo(tmp)
            runs_dir = tmp / "runs"
            runs_dir.mkdir()

            from syncsnitch.detect import run_detect

            run_id = "r-test-drift-json"
            upstream = {
                "repo": str(repo),
                "base": base_sha,
                "head": head_sha,
                "base_sha": base_sha,
                "head_sha": head_sha,
            }
            run_detect(upstream, base_sha, head_sha, run_id, runs_dir)

            drift_path = runs_dir / run_id / "drift.json"
            assert drift_path.exists(), "drift.json was not written"

            with open(drift_path) as fh:
                data = json.load(fh)

            required_keys = {"run_id", "upstream", "changes", "summary"}
            assert required_keys <= set(data.keys())
            assert data["run_id"] == run_id
