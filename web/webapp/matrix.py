import importlib
import json
from pathlib import Path
from fastapi.testclient import TestClient
import httpx
from .vendor import load

def get_latest_container_verification() -> dict:
    runs_dir = Path(__file__).resolve().parent.parent / "runs"
    runs = []
    for f in runs_dir.glob("*.json"):
        if f.name.startswith("_"):  # the sample run is illustrative, not a recorded container run
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("verification"):
                runs.append(d)
        except Exception:
            continue
    runs.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    if runs:
        v = runs[0].get("verification", {})
        return {
            "v3": next((c for c in v.get("checks", []) if c.get("id") == "V3"), None),
            "v4": next((c for c in v.get("checks", []) if c.get("id") == "V4"), None),
            "run_id": runs[0].get("run_id"),
        }
    return {}

def run_cell(billing_alias: str, orders_alias: str) -> dict:
    load(orders_alias)
    orders_rest = importlib.import_module(f"{orders_alias}.rest")
    orders_app = orders_rest.create_app("sqlite+pysqlite:///:memory:", init_schema=True, seed=True)

    load(billing_alias)
    billing_api = importlib.import_module(f"{billing_alias}.api")
    billing_app = billing_api.create_app(
        orders_rest_url="http://orders",
        orders_rest_transport=httpx.ASGITransport(app=orders_app),
    )

    client = TestClient(billing_app, raise_server_exceptions=False)
    r1 = client.post("/invoices/o-1001")
    r2 = client.post("/invoices/o-1002")

    is_ok = False
    if r1.status_code == 201 and r2.status_code == 409:
        try:
            body = r1.json()
            if body.get("total_minor") == 2164:
                is_ok = True
        except Exception:
            pass

    verdict = "ok" if is_ok else "broken"
    combined_body = f"o-1001 [{r1.status_code}]: {r1.text[:90]} | o-1002 [{r2.status_code}]: {r2.text[:90]}"[:200]

    return {
        "status_code": r1.status_code,
        "body": combined_body,
        "verdict": verdict,
    }

def get_matrix() -> dict:
    matrix = {
        "before": {
            "v1": run_cell("billing_before", "orders_v1"),
            "v2": run_cell("billing_before", "orders_v2"),
        },
        "after": {
            "v1": run_cell("billing_after", "orders_v1"),
            "v2": run_cell("billing_after", "orders_v2"),
        },
        "container_runs": get_latest_container_verification(),
    }
    return matrix
