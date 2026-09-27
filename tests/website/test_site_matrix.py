"""The lineup: the before/after x v1/v2 matrix of a real run, every cell from that run's own results."""
import json

from fastapi.testclient import TestClient

from web.webapp import history, live
from web.webapp.main import app

client = TestClient(app)
RUN = "w-20260927-101500-beef"
JUNIT_V2 = ('<testsuites><testsuite><testcase name="test_invoice_paid_order"/>'
            '<testcase name="test_revenue_report"><failure message="UndefinedColumn: column &quot;total_price&quot; '
            'does not exist">trace</failure></testcase></testsuite></testsuites>')


def _run(tmp_path, monkeypatch, local=False):
    art = {"run_id": RUN, "created_at": "2026-09-27T10:15:00+00:00", "companion_pr_url": None,
           "drift": {"changes": [{"id": "rest:Order.total_price:property_removed", "surface": "rest", "breaking": True},
                                 {"id": "grpc:orders.OrderSummary.3:field_removed", "surface": "grpc", "breaking": True},
                                 {"id": "rest:Money:schema_added", "surface": "rest", "breaking": False}]},
           "impact": {"endpoints": [{"endpoint": "GET /payments/{order_id}/status", "failure": "silent",
                                     "why": "total_price reads 0.0"}]},
           "verification": {"checks": [{"id": "V1", "status": "pass", "details": "8 passed"},
                                       {"id": "V3", "status": "pass", "details": "5/5 passed"},
                                       {"id": "V4", "status": "fail", "details": "4/5 passed"}]},
           "verdict": {"verdict": "red"}}
    web_runs, runs = tmp_path / "web-runs", tmp_path / "runs"
    web_runs.mkdir()
    (web_runs / f"{RUN}.json").write_text(json.dumps(art))
    monkeypatch.setattr(live, "WEB_RUNS", web_runs)
    monkeypatch.setattr(live, "RUNS_DIR", runs)
    if local:  # this machine's run folder holds the per-test container results
        (runs / RUN / "results").mkdir(parents=True)
        (runs / RUN / "results" / "junit-v2.xml").write_text(JUNIT_V2)
        monkeypatch.setattr(history, "LIVE_SOURCES", True)
        monkeypatch.setattr(history, "_cloud", lambda: {})
        monkeypatch.setattr(live, "ON_VERCEL", False)


def test_the_lineup_is_built_from_a_real_run(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch)
    data = client.get("/api/matrix").json()
    assert data["run"]["run_id"] == RUN and data["breaking"] == 2 and data["by_surface"] == {"rest": 1, "grpc": 1}
    assert data["before"]["v1"]["status"] == "clean"
    assert data["before"]["v2"]["status"] == "broken" and data["before"]["v2"]["endpoints"][0]["failure"] == "silent"
    assert (data["after"]["v1"]["status"], data["after"]["v1"]["details"]) == ("clean", "5/5 passed")
    assert (data["after"]["v2"]["status"], data["after"]["v2"]["details"]) == ("broken", "4/5 passed")
    page = client.get("/matrix")
    assert page.status_code == 200 and RUN in page.text and "Broken" in page.text


def test_the_lineup_shows_each_container_test(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, local=True)
    tests = client.get("/api/matrix", params={"run": RUN}).json()["after"]["v2"]["tests"]
    assert [(t["name"], t["status"]) for t in tests] == [("test_invoice_paid_order", "pass"), ("test_revenue_report", "fail")]
    assert "total_price" in tests[1]["message"]
    assert "test_revenue_report" in client.get("/matrix").text


def test_without_runs_the_lineup_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "WEB_RUNS", tmp_path)
    assert client.get("/api/matrix").json()["run"] is None
    assert "No verified run yet" in client.get("/matrix").text
