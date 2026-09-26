"""Run 3 Agents -> /live/<run_id>: S0-S2 on the site, then every later stage read from real run files and git."""
import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from web.webapp import live
from web.webapp.main import app


@pytest.fixture
def client(monkeypatch, tmp_path, fake_github_client):
    monkeypatch.setattr(live, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(live, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(live, "WEB_RUNS", tmp_path / "web-runs")
    monkeypatch.setattr(live, "ON_VERCEL", True)  # run S0-S2 inside the request (no background thread in tests)
    return TestClient(app)


def launch(client) -> tuple[str, str]:
    r = client.post("/api/launch", json={"link": "https://github.com/o/r"})
    assert r.status_code == 200, r.text
    return r.json()["run_id"], r.json()["url"]


def state(client, run_id: str) -> dict:
    r = client.get(f"/api/live/{run_id}")
    assert r.status_code == 200, r.text
    return r.json()


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True,
                   capture_output=True)


def test_launch_runs_s0_to_s2_then_hands_over_to_the_runner(client):
    """On Vercel the agents cannot run: the page says so (locally the runner starts them: test_site_agents.py)."""
    run_id, url = launch(client)
    assert url.startswith(f"/live/{run_id}?link=")
    s = state(client, run_id)
    assert s["phase"] == "blocked"
    assert s["runner"]["state"] == "blocked" and s["runner"]["problems"][0]["id"] == "vercel"
    assert s["tracer"]["status"] == "waiting_bob"
    assert (s["tracer"]["breaking"], s["tracer"]["surfaces"]) == (9, ["REST", "gRPC", "DB"])
    assert s["tracer"]["endpoints"] == ["GET /payments/{order_id}/status", "GET /reports/revenue",
                                        "POST /invoices/{order_id}"]
    assert (s["transformer"]["status"], s["verifier"]["status"]) == ("waiting", "waiting")
    assert all(c["status"] == "waiting" for c in s["verifier"]["checks"])
    assert s["spec"]["bob_command"].startswith("/syncsnitch http") and f"run={run_id}" in s["spec"]["bob_command"]
    msgs = [e["msg"] for e in s["events"]]
    assert msgs[0] == "Target received: https://github.com/o/r"
    assert any(m.startswith("S1 detect: 9 breaking of") for m in msgs)
    assert any(m.startswith("S2 trace:") and "POST /invoices/{order_id}" in m for m in msgs)
    assert (live.RUNS_DIR / run_id / "drift.json").exists() and (live.RUNS_DIR / run_id / "candidates.json").exists()
    page = client.get(url)
    assert page.status_code == 200 and "Multi-Agent Orchestrator" in page.text


def test_live_page_follows_the_bob_run(client):
    run_id, _ = launch(client)
    run_dir = live.RUNS_DIR / run_id
    ev = live._engine_events()

    ev.emit(live.RUNS_DIR, run_id, "S3", "tracer", "Tracer started")
    s = state(client, run_id)
    assert (s["phase"], s["tracer"]["status"]) == ("active", "running")

    (run_dir / "impact.json").write_text(json.dumps({"endpoints": [
        {"endpoint": "POST /invoices/{order_id}", "failure": "loud"},
        {"endpoint": "GET /payments/{order_id}/status", "failure": "silent"},
        {"endpoint": "GET /reports/revenue", "failure": "loud"}]}))
    s = state(client, run_id)
    assert (s["tracer"]["status"], s["tracer"]["loud"], s["tracer"]["silent"]) == ("done", 2, 1)
    assert s["transformer"]["status"] == "waiting"

    # the Transformer works in Bob's clone on branch syncsnitch/<run_id>
    work = live.WORK_DIR / run_id
    (work / "cons").mkdir(parents=True)
    git(work, "init", "-b", "feat")
    (work / "cons" / "invoice.py").write_text('NOT_PAYABLE = {"PENDING"}\n')
    git(work, "add", ".")
    git(work, "commit", "-m", "consumer v1")
    git(work, "checkout", "-b", f"syncsnitch/{run_id}")
    s = state(client, run_id)
    assert s["transformer"]["status"] == "running"
    (work / "cons" / "invoice.py").write_text('NOT_PAYABLE = {"PENDING", "AWAITING_PAYMENT"}\nX = 1\n')
    git(work, "commit", "-am", "fix(contract): tolerant reader")
    s = state(client, run_id)
    t = s["transformer"]
    assert (t["status"], t["files"], t["insertions"], t["deletions"]) == ("done", 1, 2, 1)
    assert any("fix(contract): tolerant reader" in e["msg"] for e in s["events"])

    checks = [{"id": f"V{i}", "name": "n", "status": "pass", "details": "ok"} for i in range(1, 7)]
    checks[2]["status"] = checks[3]["status"] = checks[4]["status"] = "skip"
    (run_dir / "verification.json").write_text(json.dumps({"checks": checks, "summary": {}}))
    s = state(client, run_id)
    assert s["verifier"]["status"] == "running"
    assert [c["status"] for c in s["verifier"]["checks"]] == ["pass", "pass", "skip", "skip", "skip", "pass"]
    assert s["transformer"]["unit_tests"] == "pass"

    (run_dir / "verdict.json").write_text(json.dumps({"verdict": "green", "reasons": ["all checks passed"]}))
    ev.emit(live.RUNS_DIR, run_id, "S7", "human", "Waiting for human approval in IBM Bob")
    s = state(client, run_id)
    assert (s["verifier"]["status"], s["verifier"]["verdict"], s["phase"]) == ("done", "green", "approval")

    ev.emit(live.RUNS_DIR, run_id, "S7", "human", "Approved by the human", "ok")
    live.WEB_RUNS.mkdir()
    (live.WEB_RUNS / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "created_at": "2099-01-01T00:00:00+00:00", "companion_pr_url": "https://github.com/o/r/pull/7"}))
    s = state(client, run_id)
    assert (s["phase"], s["companion_pr_url"], s["replay_url"]) == ("complete", "https://github.com/o/r/pull/7",
                                                                    f"/runs/{run_id}")


def test_rebuilds_a_run_from_its_url(client):
    """Serverless: a poll that lands on another instance rebuilds S0-S2 from the URL."""
    run_id, url = launch(client)
    for f in (live.RUNS_DIR / run_id).iterdir():
        f.unlink()
    (live.RUNS_DIR / run_id).rmdir()
    assert client.get(url.replace(f"/live/{run_id}", f"/api/live/{run_id}")).json()["tracer"]["breaking"] == 9


def test_bad_links_and_ids(client):
    assert client.post("/api/launch", json={"link": "https://gitlab.com/o/r"}).status_code == 400
    assert client.post("/api/launch", json={"link": "https://github.com/o/r", "upstream": "../etc"}).status_code == 400
    assert client.get("/live/w-20990101-000000-abcd").status_code == 404
    assert client.get("/api/live/..%2Fetc").status_code in (400, 404)
    r = client.post("/launch", data={"link": "nope"})
    assert r.status_code == 400
    assert 'role="alert" >paste a GitHub link' in r.text and 'value="nope"' in r.text


def test_form_fallback_redirects_to_the_live_page(client):
    r = client.post("/launch", data={"link": "https://github.com/o/r"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/live/w-")


def test_patch_diff_comes_from_the_transformer_branch(client):
    run_id, _ = launch(client)
    assert client.get(f"/api/live/{run_id}/diff").json()["diff"] == ""
    work = live.WORK_DIR / run_id
    (work / "cons").mkdir(parents=True)
    git(work, "init", "-b", "feat")
    (work / "cons" / "payments.py").write_text("amount = s.total_price\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "v1")
    git(work, "checkout", "-b", f"syncsnitch/{run_id}")
    (work / "cons" / "payments.py").write_text("amount = s.total.amount_minor\n")
    git(work, "commit", "-am", "tolerant reader")
    s = state(client, run_id)
    assert s["diff_available"] is True
    diff = client.get(f"/api/live/{run_id}/diff").json()["diff"]
    assert "-amount = s.total_price" in diff and "+amount = s.total.amount_minor" in diff


def test_open_bob_is_local_only(client, monkeypatch):
    from web.webapp import main

    monkeypatch.setattr(main, "BOBIDE", None)
    assert client.post("/api/open-bob").status_code == 503
    calls = []
    monkeypatch.setattr(main, "BOBIDE", "/usr/bin/true")
    monkeypatch.setattr(live, "ON_VERCEL", False)
    monkeypatch.setattr(main.subprocess, "Popen", lambda args, **kw: calls.append(args))
    assert client.post("/api/open-bob").status_code == 200
    assert calls == [["/usr/bin/true", str(live.REPO_ROOT)]]


def test_header_badge_names_the_serving_host(client, monkeypatch):
    """The case-files pill reads LIVE; its tooltip says which host and port is serving (real site vs a stale one)."""
    monkeypatch.setattr(live, "ON_VERCEL", False)
    home = TestClient(client.app, base_url="http://127.0.0.1:8123").get("/").text
    assert 'id="live-pill"' in home and "serving from 127.0.0.1:8123" in home


def test_replay_page_tolerates_artifacts_without_a_drift_summary(client):
    """Older engines (or a hand-written drift.json) produce artifacts without drift.summary."""
    run_id = "w-20260926-000000-abcd"
    live.WEB_RUNS.mkdir(parents=True, exist_ok=True)
    (live.WEB_RUNS / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "drift": {"changes": [{"id": "rest-1", "surface": "rest", "kind": "enum_value_removed",
                                                 "location": "OrderStatus.PENDING", "old": "PENDING", "new": None,
                                                 "breaking": True}]},
        "verification": {"checks": [{"id": "V1", "name": "unit", "status": "pass", "details": "10 passed"}]},
        "verdict": {"verdict": "green"}, "steps": []}))
    r = client.get(f"/runs/{run_id}")
    assert r.status_code == 200 and "(1 changes)" in r.text
