"""File-type specific scanners: SQL, proto, JSON fixtures."""
from __future__ import annotations

import json
import re
from pathlib import Path


def scan_sql_file(
    source: str,
    file_path: str,
    tokens: list[str],
    change_ids_by_token: dict[str, list[str]],
) -> list[dict]:
    """Scan a .sql file for whole-word column/token matches per line."""
    hits: list[dict] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        for tok in tokens:
            if re.search(r"\b" + re.escape(tok) + r"\b", line):
                hits.append({
                    "file": file_path,
                    "line": lineno,
                    "token": tok,
                    "change_ids": change_ids_by_token.get(tok, []),
                    "usage_kind": "sql_column",
                    "symbol": Path(file_path).stem,
                    "endpoints": [],
                    "in_tests": file_path.startswith("tests/") or "/tests/" in file_path,
                })
    return hits


def scan_proto_file(
    source: str,
    file_path: str,
    tokens: list[str],
    change_ids_by_token: dict[str, list[str]],
) -> list[dict]:
    """Scan a .proto file for field name matches."""
    hits: list[dict] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        for tok in tokens:
            if re.search(r"\b" + re.escape(tok) + r"\b", line):
                hits.append({
                    "file": file_path,
                    "line": lineno,
                    "token": tok,
                    "change_ids": change_ids_by_token.get(tok, []),
                    "usage_kind": "proto_field",
                    "symbol": Path(file_path).stem,
                    "endpoints": [],
                    "in_tests": file_path.startswith("tests/") or "/tests/" in file_path,
                })
    return hits


def scan_json_fixture(
    source: str,
    file_path: str,
    tokens: list[str],
    change_ids_by_token: dict[str, list[str]],
) -> list[dict]:
    """Scan a tests/*.json fixture for token occurrences."""
    hits: list[dict] = []
    try:
        data = json.loads(source)
        text = json.dumps(data)
    except json.JSONDecodeError:
        text = source

    for lineno, line in enumerate(source.splitlines(), start=1):
        for tok in tokens:
            if re.search(r"\b" + re.escape(tok) + r"\b", line):
                hits.append({
                    "file": file_path,
                    "line": lineno,
                    "token": tok,
                    "change_ids": change_ids_by_token.get(tok, []),
                    "usage_kind": "fixture",
                    "symbol": Path(file_path).stem,
                    "endpoints": [],
                    "in_tests": True,
                })
    return hits
