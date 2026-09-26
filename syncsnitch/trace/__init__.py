"""Trace package: find downstream usages of changed contract tokens and the endpoints they break."""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .files import scan_json_fixture, scan_proto_file, scan_sql_file
from .python_ast import PyFileIndex, scan_python_file

_SKIP_DIRS = {".venv", ".git", "__pycache__", "gen", "node_modules", ".pytest_cache"}
MAX_HOPS = 3


def breaking_tokens(changes: list[dict]) -> dict[str, list[str]]:
    """The "old" value of every BREAKING change -> the ids of the changes that removed it."""
    tokens: dict[str, list[str]] = {}
    for ch in changes:
        old = ch.get("old")
        if ch.get("breaking") and isinstance(old, str) and old:
            ids = tokens.setdefault(old, [])
            if ch["id"] not in ids:
                ids.append(ch["id"])
    return tokens


def _files(consumer_root: Path) -> list[str]:
    rel_paths: list[str] = []
    for dirpath, dirnames, filenames in os.walk(consumer_root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for fname in filenames:
            rel_paths.append(os.path.relpath(os.path.join(dirpath, fname), consumer_root).replace("\\", "/"))
    return rel_paths


def _scan(consumer_root: Path, rel: str, tokens: dict[str, list[str]]) -> PyFileIndex | list[dict]:
    suffix = Path(rel).suffix.lower()
    if suffix not in (".py", ".sql", ".proto", ".json"):
        return []
    if suffix == ".json" and not rel.startswith("tests/"):
        return []
    try:
        source = (consumer_root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if suffix == ".py":
        return scan_python_file(source, rel, tokens)
    if suffix == ".sql":
        return scan_sql_file(source, rel, tokens)
    if suffix == ".proto":
        return scan_proto_file(source, rel, tokens)
    return scan_json_fixture(source, rel, tokens)


class _EndpointGraph:
    """Routes reachable from a symbol by walking "who references this symbol" (consumer-wide)."""

    def __init__(self, indexes: list[PyFileIndex]):
        self.routes: dict[str, set[str]] = {}
        self.referrers: dict[str, set[str]] = {}
        self.constants: list[tuple[str, str]] = []
        for idx in indexes:
            for fn, routes in idx.routes.items():
                self.routes.setdefault(fn, set()).update(routes)
            for symbol, names in idx.references.items():
                for name in names:
                    self.referrers.setdefault(name, set()).add(symbol)
            self.constants.extend(idx.constants)

    def endpoints(self, symbols: list[str]) -> list[str]:
        found: set[str] = set()
        frontier, visited = set(symbols), set(symbols)
        for hop in range(MAX_HOPS + 1):
            for sym in frontier:
                found.update(self.routes.get(sym, ()))
            if hop == MAX_HOPS:
                break
            frontier = {r for sym in frontier for r in self.referrers.get(sym, ())} - visited
            visited |= frontier
        return sorted(found)

    def symbols_mentioning(self, text: str) -> list[str]:
        return sorted({sym for sym, value in self.constants if text in value})


def trace_consumer(changes: list[dict], consumer: str | Path) -> list[dict]:
    """Every usage of a breaking change's old token in the consumer, with the endpoints it breaks."""
    tokens = breaking_tokens(changes)
    if not tokens:
        return []
    root = Path(consumer).resolve()
    rel_paths = _files(root)
    with ThreadPoolExecutor() as pool:
        results = list(pool.map(lambda rel: _scan(root, rel, tokens), rel_paths))

    # tests are not on any request path: they neither define routes nor get endpoints
    graph = _EndpointGraph([
        r for rel, r in zip(rel_paths, results) if isinstance(r, PyFileIndex) and not rel.startswith("tests/")
    ])
    hits: list[dict] = []
    for rel, result in zip(rel_paths, results):
        if isinstance(result, PyFileIndex):
            for hit in result.hits:
                hit["endpoints"] = [] if hit["in_tests"] else graph.endpoints([hit["symbol"]])
                hits.append(hit)
        elif result:
            if rel.endswith(".sql"):
                eps = graph.endpoints(graph.symbols_mentioning(Path(rel).name))
                for hit in result:
                    hit["endpoints"] = eps
            hits.extend(result)

    hits.sort(key=lambda h: (h["file"], h["line"], h["token"]))
    return hits


def run_trace(run_id: str, consumer: str | Path, runs_dir: str | Path) -> dict:
    """Read drift.json, trace the consumer, write candidates.json and return it."""
    run_dir = Path(runs_dir) / run_id
    drift = json.loads((run_dir / "drift.json").read_text(encoding="utf-8"))
    hits = trace_consumer(drift.get("changes", []), consumer)
    candidates = {
        "run_id": run_id,
        "consumer": str(Path(consumer).resolve()),
        "hits": hits,
        "summary": {
            "hits": len(hits),
            "files": len({h["file"] for h in hits}),
            "endpoints": sorted({e for h in hits for e in h["endpoints"]}),
        },
    }
    (run_dir / "candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    return candidates
