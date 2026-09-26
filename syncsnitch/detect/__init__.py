"""Detect package: orchestrates REST, gRPC, and DB drift detection."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .openapi import diff_openapi
from .proto import diff_proto_texts
from .migrations import diff_migration_files


def run_detect(
    upstream: dict,
    base: str,
    head: str,
    run_id: str,
    runs_dir: str | Path,
) -> dict:
    """
    Detect contract drift between base and head refs.

    upstream dict keys: repo, base, head, base_sha, head_sha
    Returns the drift dict (also written to <runs_dir>/<run_id>/drift.json).
    """
    from ..gitutil import show_file, added_files  # noqa: PLC0415

    repo = upstream["repo"]

    # --- REST ---
    try:
        old_openapi = show_file(repo, base, "contracts/openapi.yaml")
        new_openapi = show_file(repo, head, "contracts/openapi.yaml")
        rest_changes = diff_openapi(old_openapi, new_openapi)
    except Exception:
        rest_changes = []

    # --- gRPC ---
    try:
        old_proto = show_file(repo, base, "contracts/orders.proto")
        new_proto = show_file(repo, head, "contracts/orders.proto")
        grpc_changes = diff_proto_texts(old_proto, new_proto)
    except Exception:
        grpc_changes = []

    # --- DB ---
    try:
        migration_paths = added_files(repo, base, head, "contracts/migrations/")
        db_changes = diff_migration_files(migration_paths) if migration_paths else []
    except Exception:
        db_changes = []

    all_changes = rest_changes + grpc_changes + db_changes

    by_surface = {
        "rest": sum(1 for c in all_changes if c["surface"] == "rest"),
        "grpc": sum(1 for c in all_changes if c["surface"] == "grpc"),
        "db": sum(1 for c in all_changes if c["surface"] == "db"),
    }
    breaking_count = sum(1 for c in all_changes if c["breaking"])

    drift = {
        "run_id": run_id,
        "upstream": upstream,
        "changes": all_changes,
        "summary": {
            "total": len(all_changes),
            "breaking": breaking_count,
            "by_surface": by_surface,
        },
    }

    out_dir = Path(runs_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "drift.json", "w", encoding="utf-8") as fh:
        json.dump(drift, fh, indent=2)

    return drift
