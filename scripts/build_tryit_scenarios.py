from pathlib import Path
from syncsnitch.detect.proto import compile_proto

def build_scenarios():
    root = Path(__file__).resolve().parent.parent
    scenarios_dir = root / "web" / "scenarios"
    ref_dir = root / "contracts" / "reference"

    # 1. REST field rename
    s1 = scenarios_dir / "rest_field_rename"
    s1.mkdir(parents=True, exist_ok=True)
    v1_openapi = (ref_dir / "v1" / "openapi.yaml").read_text(encoding="utf-8")
    (s1 / "old.yaml").write_text(v1_openapi, encoding="utf-8")
    new_field_openapi = v1_openapi.replace("customer_name:", "customer_full_name:")
    (s1 / "new.yaml").write_text(new_field_openapi, encoding="utf-8")

    # 2. REST enum rename
    s2 = scenarios_dir / "rest_enum_rename"
    s2.mkdir(parents=True, exist_ok=True)
    (s2 / "old.yaml").write_text(v1_openapi, encoding="utf-8")
    new_enum_openapi = v1_openapi.replace("PENDING", "AWAITING_PAYMENT")
    (s2 / "new.yaml").write_text(new_enum_openapi, encoding="utf-8")

    # 3. gRPC fields removed
    s3 = scenarios_dir / "grpc_fields_removed"
    s3.mkdir(parents=True, exist_ok=True)
    v1_proto = (ref_dir / "v1" / "orders.proto").read_text(encoding="utf-8")
    v2_proto = (ref_dir / "v2" / "orders.proto").read_text(encoding="utf-8")
    (s3 / "old.binpb").write_bytes(compile_proto(v1_proto))
    (s3 / "new.binpb").write_bytes(compile_proto(v2_proto))

    # 4. DB column changes
    s4 = scenarios_dir / "db_column_changes"
    s4.mkdir(parents=True, exist_ok=True)
    mig = (ref_dir / "migrations" / "0002_money_customer_status.py").read_text(encoding="utf-8")
    (s4 / "0002_money_customer_status.py").write_text(mig, encoding="utf-8")

    print("Try-it scenarios generated successfully in", scenarios_dir)

if __name__ == "__main__":
    build_scenarios()
