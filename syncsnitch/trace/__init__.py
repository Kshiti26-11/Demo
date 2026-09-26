"""Trace package: find downstream usages of changed contract tokens."""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .python_ast import scan_python_file
from .files import scan_sql_file, scan_proto_file, scan_json_fixture

_SKIP_DIRS = {".venv", ".git", "__pycache__", "gen", "node_modules", ".pytest_cache"}


def _tokens_from_changes(changes: list[dict]) -> tuple[list[str], dict[str, list[str]]]:
    """
    Extract old values of BREAKING changes as tokens.
    Returns (tokens_list, change_ids_by_token).
    """
    tokens: list[str] = []
    change_ids_by_token: dict[str, list[str]] = {}
    for ch in changes:
        if not ch.get("breaking"):
            continue
        old_val = ch.get("old")
        if old_val and isinstance(old_val, str):
            tokens.append(old_val)
            change_ids_by_token.setdefault(old_val, []).append(ch["id"])
    return tokens, change_ids_by_token


def _should_skip(path: str) -> bool:
    parts = Path(path).parts
    return any(part in _SKIP_DIRS for part in parts)


def _scan_file(
    file_path: str,
    rel_path: str,
    tokens: list[str],
    change_ids_by_token: dict[str, list[str]],
) -> list[dict]:
    suffix = Path(file_path).suffix.lower()
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if suffix == ".py":
        return scan_python_file(source, rel_path, tokens, change_ids_by_token)
    elif suffix == ".sql":
        return scan_sql_file(source, rel_path, tokens, change_ids_by_token)
    elif suffix == ".proto":
        return scan_proto_file(source, rel_path, tokens, change_ids_by_token)
    elif suffix == ".json" and (
        "tests/" in rel_path or rel_path.startswith("tests/")
    ):
        return scan_json_fixture(source, rel_path, tokens, change_ids_by_token)
    return []


def trace_consumer(
    changes: list[dict],
    consumer: str | Path,
) -> list[dict]:
    """
    Scan the consumer directory for usages of BREAKING change tokens.
    Returns a sorted list of Hit dicts.
    """
    tokens, change_ids_by_token = _tokens_from_changes(changes)
    if not tokens:
        return []

    consumer_root = Path(consumer).resolve()
    files_to_scan: list[tuple[str, str]] = []  # (abs_path, rel_path)

    for dirpath, dirnames, filenames in os.walk(consumer_root):
        # prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, consumer_root).replace("\\", "/")
            if _should_skip(rel_path):
                continue
            files_to_scan.append((abs_path, rel_path))

    hits: list[dict] = []
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_scan_file, ap, rp, tokens, change_ids_by_token): rp
            for ap, rp in files_to_scan
        }
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                hits.extend(result)

    hits.sort(key=lambda h: (h["file"], h["line"]))
    return hits


def run_trace(
    run_id: str,
    consumer: str | Path,
    runs_dir: str | Path,
) -> dict:
    """
    Load drift.json from the run dir, trace the consumer, write candidates.json.
    Returns the candidates dict.
    """
    run_dir = Path(runs_dir) / run_id
    drift_path = run_dir / "drift.json"
    with open(drift_path, encoding="utf-8") as fh:
        drift = json.load(fh)

    changes = drift.get("changes", [])
    hits = trace_consumer(changes, consumer)

    endpoint_set: set[str] = set()
    file_set: set[str] = set()
    for h in hits:
        file_set.add(h["file"])
        endpoint_set.update(h.get("endpoints", []))

    candidates = {
        "run_id": run_id,
        "consumer": str(consumer),
        "hits": hits,
        "summary": {
            "hits": len(hits),
            "files": len(file_set),
            "endpoints": sorted(endpoint_set),
        },
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "candidates.json", "w", encoding="utf-8") as fh:
        json.dump(candidates, fh, indent=2)

    return candidates
