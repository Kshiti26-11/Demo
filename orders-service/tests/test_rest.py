import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from orders_service.rest import create_app

OPENAPI_PATH = Path(__file__).parent.parent / "contracts" / "openapi.yaml"


@pytest.fixture(scope="module")
def client():
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        init_schema=True,
        seed=True,
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def order_schema():
    spec = yaml.safe_load(OPENAPI_PATH.read_text())
    # Register the full OpenAPI doc at a base URI so $ref resolution works
    base_uri = "https://orders-service/openapi.yaml"
    resource = Resource.from_contents(spec, default_specification=DRAFT202012)
    registry = Registry().with_resource(base_uri, resource)
    # The Order schema $ref uses fragment-only refs; embed full spec as validator schema
    # so the validator's resolver base matches the registry URI
    return Draft202012Validator(
        {"$ref": f"{base_uri}#/components/schemas/Order"},
        registry=registry,
    )


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_orders_ids(client):
    r = client.get("/orders")
    assert r.status_code == 200
    ids = [o["order_id"] for o in r.json()]
    assert ids == ["o-1001", "o-1002", "o-1003", "o-1004"]


def test_order_1001_matches_openapi_example(client):
    r = client.get("/orders/o-1001")
    assert r.status_code == 200
    data = r.json()
    assert data["order_id"] == "o-1001"
    assert data["customer_name"] == "Ada Lovelace"
    assert data["total_price"] == 19.99
    assert data["status"] == "PAID"
    assert data["created_at"] == "2026-09-01T10:00:00Z"


def test_order_1002_pending(client):
    r = client.get("/orders/o-1002")
    assert r.status_code == 200
    assert r.json()["status"] == "PENDING"


def test_order_not_found(client):
    r = client.get("/orders/o-9999")
    assert r.status_code == 404
    assert r.json() == {"detail": "order not found"}


def test_all_orders_valid_schema(client, order_schema):
    r = client.get("/orders")
    for order in r.json():
        errors = list(order_schema.iter_errors(order))
        assert errors == [], f"Schema errors for {order['order_id']}: {errors}"
