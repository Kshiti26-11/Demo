from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
from typing import Any

from .files import scan_json_fixture_file, scan_proto_file, scan_sql_file
from .python_ast import build_endpoint_resolver, scan_python_file

IGNORED_DIRS = {".venv", ".git", "__pycache__", "gen", "node_modules", ".pytest_cache", ".syncsnitch"}


def _is_ignored(path: Path) -> bool:
    for part in path.parts:
        if part in IGNORED_DIRS:
            return True
    return False


def trace_consumer(changes: list[dict[str, Any]], consumer: Path) -> list[dict[str, Any]]:
    consumer_path = Path(consumer).resolve()

    # Tokens = the "old" value of every BREAKING change (token -> list of change ids)
    token_map: dict[str, list[str]] = {}
    for c in changes:
        if c.get("breaking") and c.get("old"):
            tok = str(c["old"])
            token_map.setdefault(tok, []).append(c["id"])

    if not token_map:
        return []

    # Collect all python files first to build resolver
    py_files: list[Path] = []
    sql_files: list[Path] = []
    proto_files: list[Path] = []
    fixture_files: list[Path] = []

    for p in consumer_path.rglob("*"):
        if p.is_file() and not _is_ignored(p.relative_to(consumer_path)):
            if p.suffix == ".py":
                py_files.append(p)
            elif p.suffix == ".sql":
                sql_files.append(p)
            elif p.suffix == ".proto":
                proto_files.append(p)
            elif p.suffix == ".json" and "tests" in p.parts:
                fixture_files.append(p)

    # Pre-read python contents
    py_contents: dict[str, str] = {}
    for py in py_files:
        rel = py.relative_to(consumer_path).as_posix()
        try:
            py_contents[rel] = py.read_text(encoding="utf-8")
        except Exception:
            continue

    resolver = build_endpoint_resolver(py_contents)

    all_hits: list[dict[str, Any]] = []

    def scan_file(file_path: Path):
        rel = file_path.relative_to(consumer_path).as_posix()
        if file_path.suffix == ".py":
            return scan_python_file(file_path, rel, token_map, resolver)
        elif file_path.suffix == ".sql":
            return scan_sql_file(file_path, rel, token_map, py_contents, resolver)
        elif file_path.suffix == ".proto":
            return scan_proto_file(file_path, rel, token_map)
        elif file_path.suffix == ".json":
            return scan_json_fixture_file(file_path, rel, token_map)
        return []

    all_target_files = py_files + sql_files + proto_files + fixture_files
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(scan_file, all_target_files)
        for r in results:
            all_hits.extend(r)

    # Sort hits by (file, line)
    all_hits.sort(key=lambda h: (h["file"], h["line"]))
    return all_hits


def run_trace(run_id: str, consumer: Path, runs_dir: Path) -> dict[str, Any]:
    run_folder = runs_dir / run_id
    drift_file = run_folder / "drift.json"
    if not drift_file.exists():
        raise FileNotFoundError(f"Missing drift.json at {drift_file}")

    drift_data = json.loads(drift_file.read_text(encoding="utf-8"))
    changes = drift_data.get("changes", [])

    consumer_path = Path(consumer).resolve()
    hits = trace_consumer(changes, consumer_path)

    unique_files = sorted(set(h["file"] for h in hits))
    unique_endpoints = sorted(set(ep for h in hits for ep in h.get("endpoints", [])))

    candidates: dict[str, Any] = {
        "run_id": run_id,
        "consumer": str(consumer_path),
        "hits": hits,
        "summary": {
            "hits": len(hits),
            "files": unique_files,
            "endpoints": unique_endpoints,
        },
    }

    out_file = run_folder / "candidates.json"
    out_file.write_text(json.dumps(candidates, indent=2), encoding="utf-8")

    # Try copying RFC docx into run folder if found in reference or upstream
    docx_candidates = [
        Path("contracts/reference/orders-v2-change-proposal.docx"),
        consumer_path.parent / "syncsnitch" / "contracts" / "reference" / "orders-v2-change-proposal.docx",
        consumer_path.parent / "orders-service" / "docs" / "orders-v2-change-proposal.docx",
    ]
    for dc in docx_candidates:
        if dc.exists():
            shutil.copy(dc, run_folder / "change-proposal.docx")
            break

    return candidates
