from pathlib import Path
import re
from typing import Any


def scan_sql_file(path: Path, relative_path: str, token_map: dict[str, list[str]], py_contents: dict[str, str], resolver: Any) -> list[dict[str, Any]]:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return []

    sql_filename = path.name
    # Find any symbol in python files that mentions this sql filename
    referencing_symbols = set()
    for py_file, py_text in py_contents.items():
        if sql_filename in py_text:
            # Simple scan for function or assignment names in that file
            for line in py_text.splitlines():
                m_def = re.match(r"^\s*(?:async\s+)?def\s+([A-Za-z0-9_]+)", line)
                if m_def:
                    referencing_symbols.add(m_def.group(1))
                m_assign = re.match(r"^([A-Za-z0-9_]+)\s*=", line)
                if m_assign:
                    referencing_symbols.add(m_assign.group(1))

    # Resolve endpoints for those symbols
    endpoints = set()
    for sym in referencing_symbols:
        for ep in resolver(sym, ""):
            endpoints.add(ep)
    sorted_endpoints = sorted(endpoints)

    hits: list[dict[str, Any]] = []
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        for token in token_map:
            if re.search(rf"\b{re.escape(token)}\b", line):
                hits.append({
                    "file": Path(relative_path).as_posix(),
                    "line": idx,
                    "token": token,
                    "change_ids": token_map[token],
                    "usage_kind": "sql_column",
                    "symbol": path.stem,
                    "endpoints": sorted_endpoints,
                    "in_tests": Path(relative_path).as_posix().startswith("tests/"),
                })
    return hits


def scan_proto_file(path: Path, relative_path: str, token_map: dict[str, list[str]]) -> list[dict[str, Any]]:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return []

    hits: list[dict[str, Any]] = []
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        for token in token_map:
            if re.search(rf"\b{re.escape(token)}\b", line):
                hits.append({
                    "file": Path(relative_path).as_posix(),
                    "line": idx,
                    "token": token,
                    "change_ids": token_map[token],
                    "usage_kind": "proto_field",
                    "symbol": path.stem,
                    "endpoints": [],
                    "in_tests": Path(relative_path).as_posix().startswith("tests/"),
                })
    return hits


def scan_json_fixture_file(path: Path, relative_path: str, token_map: dict[str, list[str]]) -> list[dict[str, Any]]:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return []

    hits: list[dict[str, Any]] = []
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        for token in token_map:
            if f'"{token}"' in line:
                hits.append({
                    "file": Path(relative_path).as_posix(),
                    "line": idx,
                    "token": token,
                    "change_ids": token_map[token],
                    "usage_kind": "fixture",
                    "symbol": path.stem,
                    "endpoints": [],
                    "in_tests": True,
                })
    return hits
