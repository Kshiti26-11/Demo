from fastapi.testclient import TestClient
from web.webapp.main import app

client = TestClient(app)

def test_site_matrix_api():
    r = client.get("/api/matrix")
    assert r.status_code == 200
    data = r.json()
    assert data["before"]["v1"]["verdict"] == "ok"
    assert data["before"]["v2"]["verdict"] == "broken"
