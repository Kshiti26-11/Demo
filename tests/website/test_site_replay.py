from fastapi.testclient import TestClient
from web.webapp.main import app

client = TestClient(app)

def test_site_home():
    r = client.get("/")
    assert r.status_code == 200
    assert "SyncSnitch" in r.text
    assert "An upstream team changed a contract" in r.text

def test_site_runs_list():
    r = client.get("/runs")
    assert r.status_code == 200
    assert "_sample" in r.text

def test_site_run_detail_sample():
    r = client.get("/runs/_sample")
    assert r.status_code == 200
    assert "V4" in r.text
    assert "POST /invoices/{order_id}" in r.text

def test_site_run_detail_404():
    r = client.get("/runs/nope")
    assert r.status_code == 404

def test_site_api_run_detail():
    r = client.get("/api/runs/_sample")
    assert r.status_code == 200
    assert r.json()["run_id"] == "_sample"

def test_site_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
