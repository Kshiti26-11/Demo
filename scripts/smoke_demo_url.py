import sys
import httpx

def main():
    if len(sys.argv) < 2:
        print("Usage: python smoke_demo_url.py <base_url>")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    print(f"Running smoke test against: {base_url}")

    with httpx.Client(base_url=base_url, timeout=30) as client:
        # 1. Check /
        r = client.get("/")
        assert r.status_code == 200, f"/ failed: {r.status_code}"
        print("  [OK] / ok")

        # 2. Check /runs
        r = client.get("/runs")
        assert r.status_code == 200, f"/runs failed: {r.status_code}"
        print("  [OK] /runs ok")

        # 3. Check /matrix
        r = client.get("/matrix")
        assert r.status_code == 200, f"/matrix failed: {r.status_code}"
        print("  [OK] /matrix ok")

        # 4. Check /api/matrix
        r = client.get("/api/matrix")
        assert r.status_code == 200, f"/api/matrix failed: {r.status_code}"
        matrix = r.json()
        assert matrix["before"]["v1"]["verdict"] == "ok", "before x v1 must be ok"
        assert matrix["before"]["v2"]["verdict"] == "broken", "before x v2 must be broken"
        print("  [OK] /api/matrix ok (before x v2 is broken)")

        # 5. Check /health
        r = client.get("/health")
        assert r.status_code == 200 and r.json().get("status") == "ok", "/health failed"
        print("  [OK] /health ok")

        # 6. Check POST /api/try for all 4 scenarios
        scenarios = ["rest_field_rename", "rest_enum_rename", "grpc_fields_removed", "db_column_changes"]
        for sc in scenarios:
            r = client.post("/api/try", json={"scenario": sc})
            assert r.status_code == 200, f"/api/try {sc} failed: {r.status_code}"
            data = r.json()
            assert len(data.get("changes", [])) >= 1, f"/api/try {sc} returned no changes"
            print(f"  [OK] /api/try {sc} ok ({len(data['changes'])} changes, {len(data.get('hits', []))} hits)")

    print("All smoke test checks passed successfully!")
    sys.exit(0)

if __name__ == "__main__":
    main()
