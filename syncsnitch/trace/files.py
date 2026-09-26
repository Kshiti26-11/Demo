"""File-type specific scanners: SQL, proto, JSON fixtures (whole-word, line by line)."""
from __future__ import annotations

import re
from pathlib import Path


def _scan_lines(
    source: str,
    file_path: str,
    tokens: dict[str, list[str]],
    usage_kind: str,
    pattern: str,
) -> list[dict]:
    hits: list[dict] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        for tok, change_ids in tokens.items():
            if re.search(pattern.format(re.escape(tok)), line):
                hits.append({
                    "file": file_path,
                    "line": lineno,
                    "token": tok,
                    "change_ids": change_ids,
                    "usage_kind": usage_kind,
                    "symbol": Path(file_path).name,
                    "endpoints": [],
                    "in_tests": file_path.startswith("tests/"),
                })
    return hits


def scan_sql_file(source: str, file_path: str, tokens: dict[str, list[str]]) -> list[dict]:
    """*.sql: whole-word column/value matches."""
    return _scan_lines(source, file_path, tokens, "sql_column", r"\b{}\b")


def scan_proto_file(source: str, file_path: str, tokens: dict[str, list[str]]) -> list[dict]:
    """*.proto: field and enum-value names (comments ignored)."""
    code = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
    return _scan_lines(code, file_path, tokens, "proto_field", r"\b{}\b")


def scan_json_fixture(source: str, file_path: str, tokens: dict[str, list[str]]) -> list[dict]:
    """tests/**/*.json: lines containing the quoted token (a key or a string value)."""
    return _scan_lines(source, file_path, tokens, "fixture", r'"{}"')
