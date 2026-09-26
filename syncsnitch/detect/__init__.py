"""Detect package: orchestrates REST, gRPC, and DB drift detection."""
from __future__ import annotations

import json
from pathlib import Path

from ..gitutil import added_files, resolve_ref, show_file
from .migrations import diff_migrations
from .openapi import diff_openapi
from .proto import diff_proto_texts

OPENAPI_PATH = "contracts/openapi.yaml"
PROTO_PATH = "contracts/orders.proto"
MIGRATIONS_GLOB = "migrations/versions/*.py"


def _summary(changes: list[dict]) -> dict:
    return {
        "total": len(changes),
        "breaking": sum(1 for c in changes if c["breaking"]),
        "by_surface": {s: sum(1 for c in changes if c["surface"] == s) for s in ("rest", "grpc", "db")},
    }


def run_detect(upstream: str | Path, base: str, head: str, run_id: str, runs_dir: str | Path) -> dict:
    """
    Detect contract drift in the upstream checkout between two refs.

    Reads contracts/openapi.yaml and contracts/orders.proto at both refs (a surface is skipped when the file
    is missing at either ref) and the migrations/versions/*.py files ADDED between base and head.
    Writes <runs_dir>/<run_id>/drift.json and returns it.
    """
    upstream = Path(upstream["repo"] if isinstance(upstream, dict) else upstream).resolve()
    base_sha = resolve_ref(upstream, base)
    head_sha = resolve_ref(upstream, head)

    changes: list[dict] = []

    old_openapi = show_file(upstream, base_sha, OPENAPI_PATH)
    new_openapi = show_file(upstream, head_sha, OPENAPI_PATH)
    if old_openapi is not None and new_openapi is not None:
        changes += diff_openapi(old_openapi, new_openapi)

    old_proto = show_file(upstream, base_sha, PROTO_PATH)
    new_proto = show_file(upstream, head_sha, PROTO_PATH)
    if old_proto is not None and new_proto is not None:
        changes += diff_proto_texts(old_proto, new_proto)

    added = added_files(upstream, base_sha, head_sha, ".")
    migration_files = [
        (path, show_file(upstream, head_sha, path) or "")
        for path in added
        if "migration" in path and path.endswith(".py")
    ]
    changes += diff_migrations(migration_files)

    drift = {
        "run_id": run_id,
        "upstream": {
            "repo": str(upstream),
            "base": base,
            "head": head,
            "base_sha": base_sha,
            "head_sha": head_sha,
        },
        "changes": changes,
        "summary": _summary(changes),
    }

    out_dir = Path(runs_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "drift.json").write_text(json.dumps(drift, indent=2), encoding="utf-8")
    return drift
