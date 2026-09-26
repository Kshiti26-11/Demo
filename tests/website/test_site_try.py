import sys
from fastapi.testclient import TestClient
from web.webapp.main import app

client = TestClient(app)

def test_site_try_scenarios():
    scenarios = ["rest_field_rename", "rest_enum_rename", "grpc_fields_removed", "db_column_changes"]
    for sc in scenarios:
        r = client.post("/api/try", json={"scenario": sc})
        assert r.status_code == 200
        data = r.json()
        assert len(data.get("changes", [])) >= 1

    # Verify grpc and orders_pb2 isolation
    assert "grpc" not in sys.modules, "grpc must not be imported in webapp"
    assert not any(m.endswith("orders_pb2") for m in sys.modules), "orders_pb2 must not be imported in webapp"
