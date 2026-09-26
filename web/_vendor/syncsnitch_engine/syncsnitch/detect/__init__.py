import json
from pathlib import Path
from typing import Any

from ..gitutil import added_files, resolve_ref, show_file
from .migrations import diff_migrations
from .openapi import diff_openapi
from .proto import diff_proto_texts


def run_detect(upstream: Path, base: str, head: str, run_id: str, runs_dir: Path) -> dict[str, Any]:
    upstream_path = Path(upstream).resolve()
    base_sha = resolve_ref(upstream_path, base)
    head_sha = resolve_ref(upstream_path, head)

    changes: list[dict[str, Any]] = []

    # REST
    old_openapi = show_file(upstream_path, base_sha, "contracts/openapi.yaml")
    new_openapi = show_file(upstream_path, head_sha, "contracts/openapi.yaml")
    if old_openapi and new_openapi:
        changes.extend(diff_openapi(old_openapi, new_openapi))

    # gRPC
    old_proto = show_file(upstream_path, base_sha, "contracts/orders.proto")
    new_proto = show_file(upstream_path, head_sha, "contracts/orders.proto")
    if old_proto and new_proto:
        changes.extend(diff_proto_texts(old_proto, new_proto))

    # DB Migrations
    added_migration_files = added_files(upstream_path, base_sha, head_sha, "migrations/versions/*.py")
    migration_tuples: list[tuple[str, str]] = []
    for mf in added_migration_files:
        content = show_file(upstream_path, head_sha, mf)
        if content:
            migration_tuples.append((mf, content))

    if migration_tuples:
        changes.extend(diff_migrations(migration_tuples))

    # Summary
    breaking_count = sum(1 for c in changes if c.get("breaking"))
    by_surface = {
        "rest": sum(1 for c in changes if c.get("surface") == "rest" and c.get("breaking")),
        "grpc": sum(1 for c in changes if c.get("surface") == "grpc" and c.get("breaking")),
        "db": sum(1 for c in changes if c.get("surface") == "db" and c.get("breaking")),
    }

    drift_data: dict[str, Any] = {
        "run_id": run_id,
        "upstream": {
            "repo": str(upstream_path),
            "base": base,
            "head": head,
            "base_sha": base_sha,
            "head_sha": head_sha,
        },
        "changes": changes,
        "summary": {
            "total": len(changes),
            "breaking": breaking_count,
            "by_surface": by_surface,
        },
    }

    out_folder = runs_dir / run_id
    out_folder.mkdir(parents=True, exist_ok=True)
    out_file = out_folder / "drift.json"
    out_file.write_text(json.dumps(drift_data, indent=2), encoding="utf-8")

    return drift_data
