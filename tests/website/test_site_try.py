"""Commit a crime: the real contract of a (fake) GitHub repo, edited, then S1 detect + S2 trace against its consumer."""
import sys

import pytest
from fastapi.testclient import TestClient

from web.webapp import tryit
from web.webapp.main import app


@pytest.fixture
def client(fake_github_client):
    tryit._CACHE.clear()
    return TestClient(app)


def test_the_real_contracts_and_crimes_built_from_them(client):
    r = client.get("/api/try/contracts", params={"repo": "https://github.com/o/r"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert (data["repo"], data["upstream"], data["consumer"]) == ("o/r", "up", "cons")
    assert set(data["files"]) == {"up/contracts/openapi.yaml", "up/contracts/orders.proto"}
    labels = [c["label"] for c in data["crimes"]]
    assert labels and all(c["text"] != data["files"][c["path"]] for c in data["crimes"])
    assert any(lbl.startswith("Remove field") for lbl in labels) and any(lbl.startswith("Rename ") for lbl in labels)


def test_a_crime_is_detected_and_traced_through_the_real_consumer(client):
    data = client.get("/api/try/contracts", params={"repo": "https://github.com/o/r"}).json()
    crime = next(c for c in data["crimes"] if c["label"].startswith("Remove ") and c["path"].endswith(".yaml"))
    r = client.post("/api/try", json={"repo": "https://github.com/o/r", "path": crime["path"], "text": crime["text"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["summary"]["breaking"] >= 1 and any(c["breaking"] for c in out["changes"])
    assert out["hits"] and all(h["file"] for h in out["hits"])  # the consumer (billing-service) really uses it

    same = client.post("/api/try", json={"repo": "o/r", "path": crime["path"], "text": data["files"][crime["path"]]})
    assert same.json()["changes"] == []  # the real file unchanged: no crime
    assert client.post("/api/try", json={"repo": "o/r", "path": "cons/app.py", "text": "x"}).status_code == 400

    assert "grpc" not in sys.modules, "grpc must not be imported in webapp"
    assert not any(m.endswith("orders_pb2") for m in sys.modules), "orders_pb2 must not be imported in webapp"
