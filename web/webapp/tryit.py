"""Commit a crime: edit a real contract of a real repo and watch S1 detect + S2 trace catch it, live.

The contract files come from the repo's upstream at its head commit (OpenAPI and protobuf), the trail runs against
the repo's real consumer at the same commit. One-click "crimes" are built from the real file: rename or remove a
real property / field, drop a real enum value."""
from __future__ import annotations

import re
import shutil
import tempfile
import threading
from pathlib import Path, PurePosixPath

from . import analyze

DEFAULT_REPO = "https://github.com/kshiti26-11/demo"
_CACHE: dict[tuple, object] = {}  # (repo, sha, path) -> text; (repo, sha, "consumer:<dir>") -> consumer files
_LOCK = threading.Lock()


def _cached(key: tuple, make):
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    value = make()
    with _LOCK:
        if len(_CACHE) > 200:
            _CACHE.clear()
        _CACHE[key] = value
    return value


def _target(gh: analyze.GitHub, link: str) -> dict:
    _found, _commits, chosen = analyze.resolve(gh, link or DEFAULT_REPO)
    chosen["head_sha"] = gh.resolve(chosen["repo"], chosen["head"])
    return chosen


def _contract_paths(gh: analyze.GitHub, t: dict) -> list[str]:
    up = f"{t['upstream']}/" if t["upstream"] else ""
    return [p for p in gh.tree(t["repo"], t["head_sha"]) if p == f"{up}contracts/openapi.yaml"
            or re.fullmatch(re.escape(up) + r"contracts/[^/]+\.proto", p)]


def _raw(gh: analyze.GitHub, repo: str, sha: str, path: str) -> str | None:
    return _cached((repo, sha, path), lambda: gh.raw(repo, sha, path))


# --- one-click crimes, built from the real file -------------------------------------------------------------------

def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _openapi_crimes(path: str, text: str) -> list[dict]:
    lines, crimes, props, enums = text.splitlines(), [], [], []
    for i, line in enumerate(lines):
        if re.match(r"^\s*properties:\s*$", line):
            indent = _indent(line) + 2
            owner = next((re.match(r"^\s*([\w-]+):", lines[b]).group(1) for b in range(i - 1, -1, -1)
                          if lines[b].strip() and _indent(lines[b]) < _indent(line)
                          and re.match(r"^\s*([\w-]+):", lines[b])), "")
            for j in range(i + 1, len(lines)):
                if lines[j].strip() and _indent(lines[j]) < indent:
                    break
                k = re.match(r"^\s*([A-Za-z_][\w-]*):", lines[j])
                if k and _indent(lines[j]) == indent:
                    props.append((j, k.group(1), indent, owner))
        if re.match(r"^\s*enum:\s*$", line):
            for j in range(i + 1, len(lines)):
                v = re.match(r"^\s*-\s*([A-Za-z_]\w*)\s*$", lines[j])
                if not v:
                    break
                enums.append((j, v.group(1)))

    def block_end(j: int, indent: int) -> int:
        k = j + 1
        while k < len(lines) and (not lines[k].strip() or _indent(lines[k]) > indent):
            k += 1
        return k

    size: dict[str, int] = {}
    for *_, owner in props:
        size[owner] = size.get(owner, 0) + 1
    props.sort(key=lambda x: (-size[x[3]], x[0]))  # the biggest schema first (Order, not Health)
    seen: set[str] = set()
    for j, name, indent, _owner in props:
        if name in seen or name == "order_id" or len(crimes) >= 4:
            continue
        seen.add(name)
        renamed = lines[:j] + [lines[j].replace(f"{name}:", f"{name}_v2:", 1)] + lines[j + 1:]
        crimes.append({"label": f"Rename {name} → {name}_v2", "path": path, "text": "\n".join(renamed) + "\n"})
        crimes.append({"label": f"Remove {name}", "path": path,
                       "text": "\n".join(lines[:j] + lines[block_end(j, indent):]) + "\n"})
    for j, value in enums[1:2]:
        crimes.append({"label": f"Drop enum value {value}", "path": path,
                       "text": "\n".join(lines[:j] + lines[j + 1:]) + "\n"})
    return crimes


def _proto_crimes(path: str, text: str) -> list[dict]:
    lines, crimes, fields, values = text.splitlines(), [], 0, 0
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(?:repeated\s+|optional\s+)?[\w.]+\s+(\w+)\s*=\s*(\d+)\s*(\[[^\]]*\])?\s*;", line)
        if m and m.group(2) != "order_id" and fields < 2:
            fields += 1
            crimes.append({"label": f"Remove field {m.group(2)} (#{m.group(3)})", "path": path,
                           "text": "\n".join(lines[:i] + [f"{m.group(1)}reserved {m.group(3)};"] + lines[i + 1:]) + "\n"})
        e = re.match(r"^\s*([A-Z][A-Z0-9_]+)\s*=\s*([1-9]\d*)\s*;", line)
        if e and values < 1:
            values += 1
            crimes.append({"label": f"Rename enum value {e.group(1)}", "path": path,
                           "text": "\n".join(lines[:i] + [line.replace(e.group(1), f"{e.group(1)}_V2", 1)]
                                             + lines[i + 1:]) + "\n"})
    return crimes


def contracts(link: str) -> dict:
    """The repo's real contract files at the upstream head, and crimes built from them."""
    gh = analyze.client()
    t = _target(gh, link)
    files = {p: text for p in _contract_paths(gh, t) if (text := _raw(gh, t["repo"], t["head_sha"], p)) is not None}
    if not files:
        raise analyze.AnalyzeError("no contracts/openapi.yaml or contracts/*.proto in the upstream at its head")
    crimes = []
    for p, text in files.items():
        crimes += _proto_crimes(p, text) if p.endswith(".proto") else _openapi_crimes(p, text)
    return {**t, "files": files, "crimes": crimes}


# --- the crime scene: S1 detect on the edit, S2 trace on the real consumer --------------------------------------------

def _consumer_files(gh: analyze.GitHub, repo: str, sha: str, consumer: str) -> dict[str, str]:
    def fetch() -> dict[str, str]:
        cons = f"{consumer}/" if consumer else ""
        wanted = [p for p in gh.tree(repo, sha)
                  if p.startswith(cons) and p.endswith(analyze._TRACE_SUFFIXES)
                  and not (set(PurePosixPath(p).parts[:-1]) & analyze._SKIP_PARTS)
                  and (not p.endswith(".json") or p[len(cons):].startswith("tests/"))]
        if len(wanted) > 400:
            raise analyze.AnalyzeError(f"the consumer folder has {len(wanted)} files; the web demo traces at most 400")
        texts = analyze._parallel(lambda p: gh.raw(repo, sha, p), wanted)
        return {p[len(cons):]: t or "" for p, t in zip(wanted, texts)}
    return _cached((repo, sha, "consumer:" + consumer), fetch)


def run(link: str, path: str, text: str) -> dict:
    """Detect what the edited contract changes against the real one, and trace it through the real consumer."""
    if len(text) > 200_000:
        raise analyze.AnalyzeError("the edited contract is too large")
    gh = analyze.client()
    t = _target(gh, link)
    if path not in _contract_paths(gh, t):
        raise analyze.AnalyzeError(f"{path} is not a contract file of this upstream")
    old = _raw(gh, t["repo"], t["head_sha"], path)
    if old is None:
        raise analyze.AnalyzeError(f"could not read {path} at {t['head_sha'][:12]}")
    module = "detect.proto" if path.endswith(".proto") else "detect.openapi"
    diff = analyze._engine(module)
    changes = diff.diff_proto_texts(old, text) if path.endswith(".proto") else diff.diff_openapi(old, text)
    files = _consumer_files(gh, t["repo"], t["head_sha"], t["consumer"])
    tmp = Path(tempfile.mkdtemp(prefix="syncsnitch-try-"))
    try:
        for rel, body in files.items():
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")
        hits = analyze._engine("trace").trace_consumer(changes, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    breaking = [c for c in changes if c.get("breaking")]
    return {"repo": t["repo"], "upstream": t["upstream"], "consumer": t["consumer"], "head_sha": t["head_sha"],
            "path": path, "changes": changes, "hits": hits,
            "summary": {"changes": len(changes), "breaking": len(breaking), "files": len({h["file"] for h in hits}),
                        "endpoints": sorted({e for h in hits for e in h.get("endpoints") or []})}}
