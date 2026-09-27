"""Case files lists every real run: published replays, cloud runs in any state (red, waiting) and local runs."""
from fastapi.testclient import TestClient

from web.webapp import cloud, history, live
from web.webapp.main import app

client = TestClient(app)
CLOUD_RUN = "w-20260927-092147-9661"


def test_case_files_lists_a_red_cloud_run_that_was_never_published(tmp_path, monkeypatch):
    state = {"run_id": CLOUD_RUN, "phase": "approval", "companion_pr_url": None, "replay_url": None,
             "spec": {"link": "https://github.com/kshiti26-11/demo", "repo": "kshiti26-11/demo",
                      "upstream": "orders-service", "consumer": "billing-service", "base_sha": "15f95af008e5aa",
                      "head": "main", "created_at": "2026-09-27T09:22:03+00:00"},
             "runner": {"label": "Gemini", "model": "gemini-3.5-flash-lite", "spent": 2360874.0, "state": "approval"},
             "verifier": {"verdict": "red", "checks": [{"id": "V3", "status": "pass"}, {"id": "V4", "status": "fail"}]}}
    monkeypatch.setattr(history, "LIVE_SOURCES", True)
    monkeypatch.setattr(history, "_local", lambda: {})
    monkeypatch.setattr(cloud, "live_run_ids", lambda ttl=30.0: [CLOUD_RUN])
    monkeypatch.setattr(cloud, "remote_state", lambda run_id, ttl=2.0: state if run_id == CLOUD_RUN else None)
    monkeypatch.setattr(live, "WEB_RUNS", tmp_path)
    rows = client.get("/api/runs").json()
    assert [r["run_id"] for r in rows] == [CLOUD_RUN]
    row = rows[0]
    assert (row["verdict"], row["status"], row["engine"], row["tokens"]) == \
        ("red", "Waiting for you", "Gemini gemini-3.5-flash-lite", 2360874.0)
    assert row["details_url"].startswith(f"/live/{CLOUD_RUN}?link=")
    assert row["upstream_url"] == "https://github.com/kshiti26-11/demo/compare/15f95af008e5...main"
    page = client.get("/runs").text
    assert CLOUD_RUN in page and "Guilty · red" in page and "Live run page" in page and "_sample" not in page
