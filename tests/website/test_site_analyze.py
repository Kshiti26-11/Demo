"""Paste-a-repo flow (/analyze) against a fake GitHub: no network, no git history needed."""
import json
import sys

import pytest
from fastapi.testclient import TestClient

from web.webapp import analyze, main
from web.webapp.main import app

from conftest import BASE  # noqa: E402

@pytest.fixture
def client(monkeypatch, tmp_path, fake_github_client):
    monkeypatch.setattr(main, "get_runs_dir", lambda: tmp_path)
    return TestClient(app)


def test_paste_repo_link_runs_detect_and_trace(client):
    r = client.get("/api/analyze", params={"repo": "https://github.com/o/r"})
    assert r.status_code == 200, r.text
    data = r.json()
    res = data["result"]
    assert data["found"]["ref"] == "feat"  # main has no contracts, so the next branch is used
    assert (res["upstream"], res["consumer"], res["base_sha"], res["head"]) == ("up", "cons", BASE, "feat")
    assert res["summary"]["breaking"] == 9
    assert res["summary"]["by_surface"] == {"rest": 3, "grpc": 3, "db": 3}
    assert res["summary"]["endpoints"] == [
        "GET /payments/{order_id}/status", "GET /reports/revenue", "POST /invoices/{order_id}"]
    assert data["bob_command"].startswith("/syncsnitch http") and f"run={data['run_id']}" in data["bob_command"]
    assert analyze.valid_run_id(data["run_id"])
    assert "grpc" not in sys.modules and not any(m.endswith("orders_pb2") for m in sys.modules)


def test_analyze_page_renders(client):
    r = client.get("/analyze", params={"repo": "o/r"})
    assert r.status_code == 200
    assert "Start the 3 agents in IBM Bob" in r.text and "POST /invoices/{order_id}" in r.text


def test_home_has_repo_box(client):
    home = client.get("/").text
    assert 'action="/launch"' in home and "Run 3 Agents" in home and 'href="/analyze"' in home


@pytest.mark.parametrize("link", ["not a link", "https://gitlab.com/x", "https://github.com/o/missing"])
def test_bad_links_are_reported(client, link):
    r = client.get("/analyze", params={"repo": link})
    assert r.status_code == 400
    assert "Could not analyze" in r.text


def test_status_picks_up_the_bob_run_artifact(client, tmp_path):
    run = "w-20260926-120000-abcd"
    assert client.get("/api/analyze/status", params={"run": run}).json()["bob"] is None
    (tmp_path / f"{run}.json").write_text(json.dumps({
        "run_id": run, "companion_pr_url": "https://github.com/o/r/pull/9", "verdict": {"verdict": "green"},
        "steps": [{"id": f"S{i}", "name": "", "type": "deterministic", "status": "done"} for i in range(1, 10)],
    }))
    bob = client.get("/api/analyze/status", params={"run": run}).json()["bob"]
    assert bob["verdict"] == "green" and bob["url"] == f"/runs/{run}"
    assert client.get("/api/analyze/status", params={"run": "../etc"}).status_code == 400


def test_parse_repo_url():
    assert analyze.parse_repo_url("kshiti26-11/demo")["repo"] == "kshiti26-11/demo"
    assert analyze.parse_repo_url("https://github.com/o/r.git")["repo"] == "o/r"
    assert analyze.parse_repo_url("https://github.com/o/r/tree/feat/orders-v2")["ref"] == "feat/orders-v2"
    assert analyze.parse_repo_url("https://github.com/o/r/pull/1")["pull"] == "1"
    link = analyze.parse_repo_url("https://github.com/o/r/compare/main...feat")
    assert (link["base"], link["head"]) == ("main", "feat")
