import importlib
from pathlib import Path
from .vendor import load

def get_scenarios_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scenarios"

def run(scenario: str) -> dict:
    s_dir = get_scenarios_dir() / scenario
    if not s_dir.is_dir():
        raise ValueError(f"Unknown scenario: {scenario}")

    load("syncsnitch_engine")
    changes = []
    if scenario in ("rest_field_rename", "rest_enum_rename"):
        openapi_mod = importlib.import_module("syncsnitch_engine.detect.openapi")
        old_yaml = (s_dir / "old.yaml").read_text(encoding="utf-8")
        new_yaml = (s_dir / "new.yaml").read_text(encoding="utf-8")
        changes = openapi_mod.diff_openapi(old_yaml, new_yaml)
    elif scenario == "grpc_fields_removed":
        proto_mod = importlib.import_module("syncsnitch_engine.detect.proto")
        old_binpb = (s_dir / "old.binpb").read_bytes()
        new_binpb = (s_dir / "new.binpb").read_bytes()
        changes = proto_mod.diff_descriptor_sets(old_binpb, new_binpb)
    elif scenario == "db_column_changes":
        migrations_mod = importlib.import_module("syncsnitch_engine.detect.migrations")
        mig_files = [(f.name, f.read_text(encoding="utf-8")) for f in s_dir.glob("*.py")]
        changes = migrations_mod.diff_migrations(mig_files)

    consumer_dir = Path(__file__).resolve().parent.parent / "_vendor" / "billing_before" / "billing"
    trace_mod = importlib.import_module("syncsnitch_engine.trace")
    hits = trace_mod.trace_consumer(changes, consumer_dir)
    return {"changes": changes, "hits": hits}
