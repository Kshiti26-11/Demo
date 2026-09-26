"""The local runner: paste a link -> S1-S2 -> the three IBM Bob agents (headless Bob Shell) -> S5 -> S7 gate on the
page -> S8-S9 after approval. IBM Bob Shell and the heavy engine steps are replaced by stand-ins (fake_bob.py,
fake_engine.py); git, the clone, the branch, the push and the PR script are real (a local bare repo is the origin)."""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.webapp import agents, live
from web.webapp.main import app

HERE = Path(__file__).resolve().parent
RUN_ID = "w-20260926-120000-abcd"


def git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def script(path: Path, body: str) -> Path:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    for k, v in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
                 "GIT_COMMITTER_EMAIL": "t@example.com", "BOB_API_KEY": "test-key", "SYNCSNITCH_BOB_BUDGET": "5",
                 "SYNCSNITCH_NO_CONTAINERS": "1", "FAKE_BOB_RECORD": str(tmp_path / "bob-calls.jsonl")}.items():
        monkeypatch.setenv(k, v)
    for k in ("FAKE_BOB_FAIL", "FAKE_BOB_FIX", "FAKE_BOB_TRANSFORMER", "FAKE_BOB_UNCOMMITTED", "FAKE_BOB_VERDICT",
              "FAKE_VERIFY", "BOB_TEAM_ID", "ANTHROPIC_API_KEY", "SYNCSNITCH_AGENT_BACKEND", "SYNCSNITCH_CLAUDE_MODEL",
              "SYNCSNITCH_CLAUDE_TOKEN_BUDGET", "XAI_API_KEY", "SYNCSNITCH_GROK_MODEL", "SYNCSNITCH_TOKEN_BUDGET",
              "GEMINI_API_KEY", "SYNCSNITCH_GEMINI_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(live, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(live, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(live, "WEB_RUNS", tmp_path / "web-runs")
    monkeypatch.setattr(live, "ON_VERCEL", False)
    monkeypatch.setattr(agents, "ENV_FILES", ())
    monkeypatch.setattr(agents, "ACTIVE", tmp_path / "ACTIVE")
    monkeypatch.setattr(agents, "_engine", lambda: [sys.executable, str(HERE / "fake_engine.py")])
    bob = script(tmp_path / "bin" / "bob", f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "fake_bob.py"}" "$@"\n') \
        if (tmp_path / "bin").mkdir() is None else None
    monkeypatch.setenv("SYNCSNITCH_BOB_BIN", str(bob))
    # gh: only `gh pr create` is used (by scripts/open_companion_pr.sh); it records its arguments
    script(tmp_path / "bin" / "gh", f'#!/bin/sh\necho "$@" >> "{tmp_path}/gh-calls.txt"\n'
                                    'echo "https://github.com/o/r/pull/42"\n')
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")

    # the upstream repo: up/ = the contract owner (v1 at base, v2 on feat), cons/ = the consumer
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-q", "-b", "main")
    write(src / "up" / "contracts" / "openapi.yaml", "version: 1\n")
    write(src / "up" / "docs" / "orders-v2-change-proposal.md", "# Orders v2\nRoll out behind a flag.\n")
    write(src / "cons" / "app.py", "NOT_PAYABLE = {'PENDING'}\n")
    git(src, "add", ".")
    git(src, "commit", "-q", "-m", "v1")
    base = git(src, "rev-parse", "HEAD")
    git(src, "checkout", "-q", "-b", "feat")
    write(src / "up" / "contracts" / "openapi.yaml", "version: 2\n")
    git(src, "commit", "-q", "-am", "feat!: orders v2")
    head = git(src, "rev-parse", "HEAD")
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(src), str(origin))
    monkeypatch.setattr(agents, "_clone_cmd", lambda repo, dest: ["git", "clone", "--quiet", str(origin), str(dest)])

    # what the website's S0-S2 leaves behind for a run
    run_dir = live.RUNS_DIR / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "drift.json").write_text(json.dumps({"run_id": RUN_ID, "changes": [], "summary": {"breaking": 3}}))
    (run_dir / "candidates.json").write_text(json.dumps({"run_id": RUN_ID, "hits": []}))
    live._save_spec(RUN_ID, {
        "run_id": RUN_ID, "link": "https://github.com/o/r", "repo": "o/r", "status": "traced",
        "traced_at": "2026-09-26T12:00:01.000+00:00", "upstream": "up", "consumer": "cons", "base": base,
        "head": "feat", "base_sha": base, "head_sha": head, "default_branch": "main",
        "summary": {"total": 3, "breaking": 3, "by_surface": {"rest": 3, "grpc": 0, "db": 0}, "files": 1,
                    "endpoints": ["POST /invoices/{order_id}"]}, "hits": 2, "overrides": {}})
    return {"tmp": tmp_path, "origin": origin, "base": base, "head": head, "run_dir": run_dir,
            "client": TestClient(app)}


def run_agents(env) -> dict:
    assert agents.start(RUN_ID)
    agents._THREADS[RUN_ID].join(60)
    return state(env)


def state(env) -> dict:
    r = env["client"].get(f"/api/live/{RUN_ID}")
    assert r.status_code == 200, r.text
    return r.json()


def calls(env) -> list[dict]:
    path = env["tmp"] / "bob-calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_link_to_gate_runs_all_three_agents_with_no_bob_ide_step(env):
    s = run_agents(env)
    assert s["phase"] == "approval"
    assert (s["tracer"]["status"], s["tracer"]["loud"], s["tracer"]["silent"]) == ("done", 1, 1)
    t = s["transformer"]
    assert (t["status"], t["files"], t["commits"], t["branch"]) == ("done", 1, 1, f"syncsnitch/{RUN_ID}")
    assert (s["verifier"]["status"], s["verifier"]["verdict"]) == ("done", "green")
    assert [c["status"] for c in s["verifier"]["checks"]] == ["pass", "pass", "skip", "skip", "skip", "pass"]
    r = s["runner"]
    assert (r["state"], r["spent"], r["budget"]) == ("approval", 1.2, 5.0)
    assert (r["can_approve"], r["can_reject"]) == (True, True)
    assert r["tasks"] == {"tracer": "task-syncsnitch-tracer", "transformer": "task-syncsnitch-transformer",
                          "verifier": "task-syncsnitch-verifier"}

    made = calls(env)
    assert [c["mode"] for c in made] == ["syncsnitch-tracer", "syncsnitch-transformer", "syncsnitch-verifier"]
    assert all(c["has_key"] and c["opts"]["--trust"] and c["opts"]["--disable-subagents"] for c in made)
    assert [c["opts"]["--max-cost"] for c in made] == ["1.50", "3.85", "4.20"]  # the budget is split, never exceeded
    assert "change-proposal.md" in made[0]["prompt"] and "PR_NUMBER=null" in made[1]["prompt"]
    assert (env["run_dir"] / "change-proposal.md").read_text().startswith("# Orders v2")
    assert not agents.ACTIVE.exists()  # the write guard is released when the agents are done

    bob_lines = [e["msg"] for e in s["events"] if e.get("src") == "bob"]
    assert "Reading the run files for this step." in bob_lines  # markdown stripped, chunks joined
    assert "read_file · run/drift.json" in bob_lines
    assert any(m.startswith("$ cd ") and m.endswith("cons && uv run pytest -q") for m in bob_lines)
    assert any(m.startswith("IBM Bob session finished: 3 tool calls · 0.40 Bobcoins") for m in bob_lines)
    assert not any("thinking about it" in m for m in bob_lines)  # reasoning is not streamed
    msgs = [e["msg"] for e in s["events"]]
    assert any(m.startswith("Docker is not running on this machine") for m in msgs)
    assert any(m.startswith("Tracer done: impact.json - 2 endpoints (1 loud, 1 silent)") for m in msgs)
    assert any(m.startswith("S7 human approval gate") for m in msgs)
    assert s["diff_available"] and "NOT_PAYABLE" in env["client"].get(f"/api/live/{RUN_ID}/diff").json()["diff"]


def test_approve_pushes_the_branch_and_opens_a_draft_pr(env):
    run_agents(env)
    assert env["client"].post(f"/api/live/{RUN_ID}/approve").status_code == 200
    agents._THREADS[RUN_ID].join(60)
    s = state(env)
    assert (s["phase"], s["companion_pr_url"], s["replay_url"]) == ("complete", "https://github.com/o/r/pull/42",
                                                                    f"/runs/{RUN_ID}")
    assert git(env["origin"], "rev-parse", f"syncsnitch/{RUN_ID}")  # really pushed
    gh = (env["tmp"] / "gh-calls.txt").read_text()
    assert "pr create --draft --base feat" in gh and f"--head syncsnitch/{RUN_ID}" in gh
    assert (live.WEB_RUNS / f"{RUN_ID}.json").exists()
    msgs = [e["msg"] for e in s["events"]]
    assert "Approved by the human on the run page" in msgs
    assert "Draft companion PR opened: https://github.com/o/r/pull/42" in msgs
    assert env["client"].post(f"/api/live/{RUN_ID}/approve").status_code == 409  # only once


def test_reject_publishes_nothing(env):
    run_agents(env)
    assert env["client"].post(f"/api/live/{RUN_ID}/reject").status_code == 200
    s = state(env)
    assert (s["phase"], s["runner"]["can_approve"]) == ("aborted", False)
    assert env["client"].post(f"/api/live/{RUN_ID}/approve").status_code == 409
    assert not (env["tmp"] / "gh-calls.txt").exists()
    assert git(env["origin"], "branch", "--list", f"syncsnitch/{RUN_ID}") == ""


def test_red_verdict_gets_one_automatic_fix_round(env, monkeypatch):
    monkeypatch.setenv("FAKE_VERIFY", "fail-once")
    s = run_agents(env)
    made = calls(env)
    assert [c["mode"] for c in made] == ["syncsnitch-tracer", "syncsnitch-transformer", "syncsnitch-verifier",
                                         "syncsnitch-transformer", "syncsnitch-verifier"]
    assert "fix round" in made[3]["prompt"] and "cons/app.py: fix V1" in made[3]["prompt"]
    assert "V1 consumer unit tests: run 1" in made[3]["prompt"]
    assert (s["phase"], s["verifier"]["verdict"], s["transformer"]["commits"]) == ("approval", "green", 2)
    assert s["runner"]["can_approve"] is True
    assert s["runner"]["spent"] == 2.0  # 5 sessions x 0.40: the fix round adds to round 1, it does not replace it
    assert [c["opts"]["--max-cost"] for c in made] == ["1.50", "3.85", "4.20", "3.05", "3.40"]


def test_still_red_after_the_fix_round_keeps_the_gate_closed(env, monkeypatch):
    monkeypatch.setenv("FAKE_VERIFY", "fail")
    s = run_agents(env)
    assert (s["phase"], s["verifier"]["verdict"]) == ("approval", "red")
    assert (s["runner"]["can_approve"], s["runner"]["can_reject"]) == (False, True)
    r = env["client"].post(f"/api/live/{RUN_ID}/approve")
    assert r.status_code == 409 and "not green" in r.json()["detail"]
    assert len(calls(env)) == 5  # exactly one fix round


def test_a_fix_round_without_changes_is_judged_again_not_crashed(env, monkeypatch):
    monkeypatch.setenv("FAKE_VERIFY", "fail")
    monkeypatch.setenv("FAKE_BOB_FIX", "noop")
    s = run_agents(env)
    assert (s["phase"], s["verifier"]["verdict"], s["transformer"]["status"]) == ("approval", "red", "done")
    assert any(e["msg"].startswith("No new commit in this session") for e in s["events"])


def test_a_fix_round_session_that_errors_is_still_judged(env, monkeypatch):
    monkeypatch.setenv("FAKE_VERIFY", "fail-once")
    monkeypatch.setenv("FAKE_BOB_FIX", "fail")
    s = run_agents(env)  # the fix-round session errors, but the branch holds round 1: S5/S6 judge it (V1 run 2 passes)
    assert (s["phase"], s["verifier"]["verdict"]) == ("approval", "green")
    made = [c["mode"] for c in calls(env)]
    assert made == ["syncsnitch-tracer", "syncsnitch-transformer", "syncsnitch-verifier", "syncsnitch-transformer",
                    "syncsnitch-verifier"]


def test_while_the_fix_round_runs_the_old_verdict_is_not_shown(env):
    run_agents(env)
    spec = live._load(env["run_dir"] / "spec.json")
    spec["runner"].update(state="transformer", agents={**spec["runner"]["agents"], "transformer": "running",
                                                      "verifier": "waiting"})
    live._save_spec(RUN_ID, spec)
    agents._THREADS[RUN_ID] = type("Alive", (), {"is_alive": lambda self: True})()
    s = state(env)
    assert (s["verifier"]["status"], s["verifier"]["verdict"]) == ("waiting", None)
    assert all(c["status"] == "waiting" for c in s["verifier"]["checks"])
    del agents._THREADS[RUN_ID]


def test_the_verifier_cannot_overrule_a_failing_check(env, monkeypatch):
    monkeypatch.setenv("FAKE_VERIFY", "fail")
    monkeypatch.setenv("FAKE_BOB_VERDICT", "green")
    s = run_agents(env)
    assert s["verifier"]["verdict"] == "red"
    verdict = json.loads((env["run_dir"] / "verdict.json").read_text())
    assert verdict["reasons"][0] == "Overridden to red by the runner: V1 failed"
    assert any("overridden to RED" in e["msg"] for e in s["events"])


def test_a_failed_agent_stops_the_run_and_resume_continues_where_it_stopped(env, monkeypatch):
    monkeypatch.setenv("FAKE_BOB_FAIL", "syncsnitch-transformer")
    s = run_agents(env)
    assert (s["phase"], s["tracer"]["status"], s["transformer"]["status"]) == ("failed", "done", "failed")
    assert "the Transformer made no changes (Bob API key is invalid)" in s["runner"]["error"]
    assert s["runner"]["can_start"] is True
    assert any(e["msg"].startswith("IBM Bob session ended without a result") for e in s["events"])

    monkeypatch.delenv("FAKE_BOB_FAIL")
    assert env["client"].post(f"/api/live/{RUN_ID}/agents").status_code == 200
    agents._THREADS[RUN_ID].join(60)
    s = state(env)
    assert (s["phase"], s["runner"]["error"]) == ("approval", None)
    assert [c["mode"] for c in calls(env)].count("syncsnitch-tracer") == 1  # the finished Tracer is not re-run


def test_edits_left_uncommitted_are_committed_by_the_runner(env, monkeypatch):
    monkeypatch.setenv("FAKE_BOB_UNCOMMITTED", "1")
    s = run_agents(env)
    assert (s["transformer"]["status"], s["transformer"]["commits"]) == ("done", 1)
    assert any(e["msg"].startswith("The Transformer left edits uncommitted") for e in s["events"])


def test_a_transformer_that_changes_nothing_fails_the_run(env, monkeypatch):
    monkeypatch.setenv("FAKE_BOB_TRANSFORMER", "noop")
    s = run_agents(env)
    assert (s["phase"], s["transformer"]["status"]) == ("failed", "failed")
    assert "no new commit" in s["runner"]["error"]


def test_the_bobcoin_budget_is_enforced(env, monkeypatch):
    monkeypatch.setenv("SYNCSNITCH_BOB_BUDGET", "0.5")
    s = run_agents(env)
    assert s["phase"] == "failed" and "Bobcoin budget for this run is used up" in s["runner"]["error"]
    assert calls(env) == []


def test_missing_setup_blocks_the_run_and_says_how_to_fix_it(env, monkeypatch):
    monkeypatch.delenv("BOB_API_KEY")
    monkeypatch.delenv("SYNCSNITCH_BOB_BIN")
    monkeypatch.setattr(agents, "bob_bin", lambda: None)
    assert agents.start(RUN_ID) is False
    s = state(env)
    assert s["phase"] == "blocked" and s["runner"]["can_start"] is False
    assert [p["id"] for p in s["runner"]["problems"]] == ["gemini", "groq", "grok", "claude", "bob"]  # any engine will do
    assert s["runner"]["problems"][0]["fix"] == "bash scripts/gemini_setup.sh"
    r = env["client"].post(f"/api/live/{RUN_ID}/agents")
    assert r.status_code == 409 and "gemini_setup.sh" in r.json()["detail"]
    assert any("Cannot start the agents" in e["msg"] for e in s["events"])


def test_bob_preference_lists_what_bob_still_needs(env, monkeypatch):
    monkeypatch.setenv("SYNCSNITCH_AGENT_BACKEND", "bob")
    monkeypatch.delenv("BOB_API_KEY")
    status = agents.runner_status()
    assert (status["ready"], status["backend"], [p["id"] for p in status["problems"]]) == (False, "bob", ["key"])


def test_a_run_interrupted_by_a_restart_can_be_resumed(env):
    runner = {"state": "transformer", "agents": {"tracer": "done", "transformer": "running"}}
    spec = live._load(env["run_dir"] / "spec.json")
    live._save_spec(RUN_ID, {**spec, "runner": runner})
    s = state(env)
    assert (s["phase"], s["transformer"]["status"], s["runner"]["can_start"]) == ("interrupted", "stopped", True)


def test_runner_status_on_vercel(monkeypatch):
    monkeypatch.setattr(live, "ON_VERCEL", True)
    status = agents.runner_status()
    assert status["ready"] is False and status["problems"][0]["id"] == "vercel"


def test_api_key_comes_from_env_local(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_API_KEY", raising=False)
    (tmp_path / ".env.local").write_text("# local\nexport BOB_API_KEY='k-123'\nOTHER=x\nSYNCSNITCH_BOB_BUDGET=7\n")
    monkeypatch.setattr(agents, "ENV_FILES", (tmp_path / ".env", tmp_path / ".env.local"))
    monkeypatch.delenv("SYNCSNITCH_BOB_BUDGET", raising=False)
    assert agents.local_env() == {"BOB_API_KEY": "k-123", "SYNCSNITCH_BOB_BUDGET": "7"}
    assert agents.budget() == 7.0


def test_stream_events_become_readable_log_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "RUNS_DIR", tmp_path / "runs")
    ctx = {"run_id": RUN_ID, "work_rel": ".syncsnitch/work/x", "run_rel": ".syncsnitch/runs/x"}
    d = agents._describe_tool
    files = {"args": {"file": [{"path": ".syncsnitch/work/x/cons/a.py"}]}}
    assert d(ctx, "read_file", files) == "read_file · cons/a.py"
    assert d(ctx, "execute_command", {"command": "cd .syncsnitch/work/x/cons && uv run pytest -q"}) == \
        "$ cd cons && uv run pytest -q"
    assert d(ctx, "search_files", {"path": "cons", "regex": "total_price"}) == "search_files · cons /total_price/"
    assert d(ctx, "attempt_completion", {"result": "Done: 5 files\nmore"}) == "result: Done: 5 files"
    assert d(ctx, "update_todo_list", {"todos": "[x] read\n[ ] write"}) == "plan: [x] read · [ ] write"
    stream = agents._Stream(ctx, "transformer")
    stream.feed({"type": "error", "message": "The task reached the cost limit of 3.85 Bobcoins (spent: 3.9012)."})
    assert stream.cost == 3.9012 and stream.errors
    events = live._engine_events().read(live.RUNS_DIR, RUN_ID)
    assert events[-1]["level"] == "error" and events[-1]["src"] == "bob" and events[-1]["step"] == "S4"
