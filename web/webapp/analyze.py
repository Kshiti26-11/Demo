"""Paste a GitHub repo link -> SyncSnitch S1 (detect) + S2 (trace) live, through the GitHub API.

Works on Vercel (no git binary, no Docker, no grpcio-tools) and locally. The three AI agents (S3 Tracer,
S4 Transformer, S6 Verifier) run in IBM Bob via /syncsnitch <link to this page>; S5 (mock containers) runs in
GitHub Actions (.github/workflows/syncsnitch-analyze.yml), dispatched from here.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath

import httpx

from .vendor import load

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
# Where the SyncSnitch repo (engine, Bob layer, Actions workflow, recorded runs) lives
HOME_REPO = os.environ.get("SYNCSNITCH_REPO", "kshiti26-11/demo")
RUNS_REF = os.environ.get("SYNCSNITCH_RUNS_REF", "main")  # branch the recorded runs are pushed to
WORKFLOW = "syncsnitch-analyze.yml"
WORKFLOW_REF = os.environ.get("SYNCSNITCH_WORKFLOW_REF", "main")

_SKIP_PARTS = {".venv", ".git", "__pycache__", "gen", "node_modules", ".pytest_cache", "_vendor"}
_NOT_A_SERVICE = ("templates/", "web/", "contracts/reference/", "tests/")
_TRACE_SUFFIXES = (".py", ".sql", ".proto", ".json")
_REPO_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:github\.com/)?(?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?"
    r"(?:/(?:(?P<kind>tree|pull|compare)/(?P<rest>.+?)))?/?$"
)
_RUN_ID_RE = re.compile(r"^w-\d{8}-\d{6}-[0-9a-f]{4}$")


class AnalyzeError(Exception):
    """A problem the user can fix (bad link, private repo, nothing to analyze)."""


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

def _token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    try:  # local convenience: reuse the GitHub CLI login
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        return (out.stdout.strip() or None) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


class GitHub:
    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "syncsnitch-demo"}
        self.has_token = bool(token)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.http = httpx.Client(headers=headers, transport=transport, timeout=20, follow_redirects=True)

    def _get(self, url: str, **params):
        r = self.http.get(url, params=params or None)
        if r.status_code == 404:
            raise AnalyzeError(f"not found on GitHub: {url.removeprefix(API)} (private repo or wrong link?)")
        if r.status_code in (401, 403, 429):
            raise AnalyzeError(f"GitHub refused the request ({r.status_code}): {r.json().get('message', '')}")
        r.raise_for_status()
        return r.json()

    def repo(self, repo: str) -> dict:
        return self._get(f"{API}/repos/{repo}")

    def pull(self, repo: str, number: str) -> dict:
        return self._get(f"{API}/repos/{repo}/pulls/{number}")

    def branches(self, repo: str) -> list[str]:
        return [b["name"] for b in self._get(f"{API}/repos/{repo}/branches", per_page=100)]

    def tree(self, repo: str, ref: str) -> list[str]:
        data = self._get(f"{API}/repos/{repo}/git/trees/{ref}", recursive=1)
        return [t["path"] for t in data.get("tree", []) if t["type"] == "blob"]

    def commits(self, repo: str, ref: str, path: str) -> list[dict]:
        return self._get(f"{API}/repos/{repo}/commits", sha=ref, path=path, per_page=10)

    def compare(self, repo: str, base: str, head: str) -> list[dict]:
        return self._get(f"{API}/repos/{repo}/compare/{base}...{head}").get("files", [])

    def resolve(self, repo: str, ref: str) -> str:
        return self._get(f"{API}/repos/{repo}/commits/{ref}")["sha"]

    def raw(self, repo: str, sha: str, path: str) -> str | None:
        r = self.http.get(f"{RAW}/{repo}/{sha}/{path}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.text

    def dispatch(self, inputs: dict) -> None:
        r = self.http.post(f"{API}/repos/{HOME_REPO}/actions/workflows/{WORKFLOW}/dispatches",
                           json={"ref": WORKFLOW_REF, "inputs": inputs})
        if r.status_code != 204:
            raise AnalyzeError(f"could not start the GitHub Actions run ({r.status_code}): {r.text[:200]}")

    def find_run(self, run_id: str) -> dict | None:
        runs = self._get(f"{API}/repos/{HOME_REPO}/actions/workflows/{WORKFLOW}/runs",
                         event="workflow_dispatch", per_page=30).get("workflow_runs", [])
        return next((r for r in runs if run_id in (r.get("display_title") or "")), None)

    def run_verification(self, run: dict) -> dict | None:
        arts = self._get(run["artifacts_url"]).get("artifacts", [])
        art = next((a for a in arts if a["name"].startswith("syncsnitch-")), None)
        if not art or not self.has_token:
            return None
        r = self.http.get(art["archive_download_url"])
        if r.status_code != 200:
            return None
        with zipfile.ZipFile(BytesIO(r.content)) as zf:
            name = next((n for n in zf.namelist() if n.endswith("verification.json")), None)
            return json.loads(zf.read(name)) if name else None


def client() -> GitHub:
    """Factory (tests replace it with a GitHub on an httpx.MockTransport)."""
    return GitHub(_token())


# ---------------------------------------------------------------------------
# Discovery: which folder is the upstream, which is the consumer, which refs to compare
# ---------------------------------------------------------------------------

def parse_repo_url(url: str) -> dict:
    url = (url or "").strip()
    host = re.match(r"^(?:https?://)?([^/]+)/", url)
    if "://" in url and host and host.group(1).lower() not in ("github.com", "www.github.com"):
        raise AnalyzeError("only public github.com repositories are supported")
    m = _REPO_RE.match(url)
    if not m:
        raise AnalyzeError("paste a GitHub link like https://github.com/owner/repo")
    out = {"repo": f"{m['owner']}/{m['name']}", "ref": None, "pull": None, "base": None, "head": None}
    kind, rest = m["kind"], m["rest"]
    if kind == "tree":
        out["ref"] = rest
    elif kind == "pull":
        out["pull"] = rest.split("/")[0]
    elif kind == "compare" and "..." in rest:
        out["base"], out["head"] = rest.split("...", 1)
    return out


def _dir_of(path: str, suffix: str) -> str:
    return path[: -len(suffix)].rstrip("/")


def _service_dirs(paths: list[str]) -> tuple[list[str], list[str]]:
    """(upstream candidates, consumer candidates) - folders, "" = repo root."""
    def ok(d: str) -> bool:
        prefix = f"{d}/" if d else ""
        return not any(prefix.startswith(bad) for bad in _NOT_A_SERVICE) and not (set(PurePosixPath(d).parts) & _SKIP_PARTS)

    upstreams = sorted({_dir_of(p, "contracts/openapi.yaml") for p in paths
                        if p == "contracts/openapi.yaml" or p.endswith("/contracts/openapi.yaml")} |
                       {str(PurePosixPath(p).parent.parent) if str(PurePosixPath(p).parent.parent) != "." else ""
                        for p in paths if re.search(r"(^|/)contracts/[^/]+\.proto$", p) and "/upstream/" not in p})
    upstreams = [d for d in upstreams if ok(d)]
    # a consumer vendors the upstream contract under contracts/upstream/, or at least has Python code
    vendored = sorted({p.split("contracts/upstream/")[0].rstrip("/") for p in paths if "contracts/upstream/" in p})
    projects = sorted({_dir_of(p, "pyproject.toml") for p in paths if p == "pyproject.toml" or p.endswith("/pyproject.toml")})
    consumers = [d for d in dict.fromkeys(vendored + projects) if ok(d) and d not in upstreams]
    return upstreams, consumers


def discover(gh: GitHub, url: str) -> dict:
    """Everything the form needs: branches, upstream/consumer folders and default base/head."""
    link = parse_repo_url(url)
    repo = link["repo"]
    info = gh.repo(repo)
    branches = gh.branches(repo)
    notes: list[str] = []

    if link["pull"]:
        pr = gh.pull(repo, link["pull"])
        link["base"], link["head"] = pr["base"]["ref"], pr["head"]["ref"]
        notes.append(f"Using PR #{link['pull']}: {link['base']} → {link['head']}.")

    candidates = [link["head"] or link["ref"] or info["default_branch"]]
    candidates += [b for b in [info["default_branch"], *branches] if b not in candidates]
    for ref in candidates[:8]:
        paths = gh.tree(repo, ref)
        upstreams, consumers = _service_dirs(paths)
        if upstreams:
            if ref != candidates[0]:
                notes.append(f"No contracts on {candidates[0]}; using branch {ref}.")
            break
    else:
        raise AnalyzeError(f"no upstream contract (contracts/openapi.yaml or contracts/*.proto) found in {repo}")

    return {
        "repo": repo,
        "html_url": info.get("html_url", f"https://github.com/{repo}"),
        "default_branch": info["default_branch"],
        "branches": branches,
        "ref": ref,
        "paths": paths,
        "upstreams": upstreams,
        "consumers": consumers,
        "base": link["base"],
        "head": link["head"] or ref,
        "notes": notes,
    }


def contract_commits(gh: GitHub, repo: str, ref: str, upstream: str) -> list[dict]:
    """Recent commits on <ref> that touched the upstream's contracts or migrations (newest first)."""
    prefix = f"{upstream}/" if upstream else ""
    seen: dict[str, dict] = {}
    for path in (f"{prefix}contracts", f"{prefix}migrations"):
        for c in gh.commits(repo, ref, path):
            seen.setdefault(c["sha"], {
                "sha": c["sha"],
                "short": c["sha"][:7],
                "parent": (c.get("parents") or [{}])[0].get("sha"),
                "message": c["commit"]["message"].splitlines()[0][:72],
                "date": c["commit"]["committer"]["date"],
            })
    return sorted(seen.values(), key=lambda c: c["date"], reverse=True)


# ---------------------------------------------------------------------------
# S1 detect + S2 trace (the vendored engine - the same code the CLI runs)
# ---------------------------------------------------------------------------

def _engine(module: str):
    load("syncsnitch_engine")
    return importlib.import_module(f"syncsnitch_engine.{module}")


def new_run_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("w-%Y%m%d-%H%M%S-") + secrets.token_hex(2)


def _parallel(fn, items: list) -> list:
    with ThreadPoolExecutor(max_workers=16) as pool:
        return list(pool.map(fn, items))


def resolve(gh: GitHub, link: str, upstream: str | None = None, consumer: str | None = None,
            base: str | None = None, head: str | None = None) -> tuple[dict, list[dict], dict]:
    """(discovery, contract commits, the chosen upstream/consumer/base/head) for a pasted link."""
    found = discover(gh, link)
    upstream = upstream if upstream is not None else found["upstreams"][0]
    if upstream not in found["upstreams"]:
        raise AnalyzeError(f"no contracts in folder {upstream!r}")
    consumers = [c for c in found["consumers"] if c != upstream]
    if not consumers:
        raise AnalyzeError("no consumer folder (a Python project other than the upstream) found")
    consumer = consumer if consumer is not None else consumers[0]
    head = head or found["head"]
    commits = contract_commits(gh, found["repo"], head, upstream)
    if not base:
        base = found["base"] or (commits[0]["parent"] if commits and commits[0]["parent"] else None)
    if not base:
        raise AnalyzeError("could not pick a base: no commit changed the upstream contracts yet")
    return found, commits, {"repo": found["repo"], "upstream": upstream, "consumer": consumer, "base": base, "head": head}


def run_pipeline(gh: GitHub, repo: str, upstream: str, consumer: str, base: str, head: str,
                 consumer_ref: str | None = None, on_event=None) -> dict:
    """S1 detect + S2 trace. ``on_event(step, message, level)`` receives progress as it happens."""
    say = on_event or (lambda *_: None)
    consumer_ref = consumer_ref or head
    base_sha, head_sha, consumer_sha = _parallel(lambda ref: gh.resolve(repo, ref), [base, head, consumer_ref])
    head_paths, consumer_paths, compared = _parallel(lambda job: job(), [
        lambda: gh.tree(repo, head_sha),
        lambda: gh.tree(repo, consumer_sha) if consumer_sha != head_sha else None,
        lambda: gh.compare(repo, base_sha, head_sha),
    ])
    consumer_paths = consumer_paths if consumer_paths is not None else head_paths

    up = f"{upstream}/" if upstream else ""
    openapi = f"{up}contracts/openapi.yaml"
    protos = sorted(p for p in head_paths if re.fullmatch(re.escape(up) + r"contracts/[^/]+\.proto", p))
    migrations = sorted(f["filename"] for f in compared if f["status"] == "added"
                        and re.fullmatch(re.escape(up) + r"migrations/versions/[^/]+\.py", f["filename"]))
    # S2 reads only these consumer files (the same filter the tracer applies on disk)
    cons = f"{consumer}/" if consumer else ""
    wanted = [p for p in consumer_paths
              if p.startswith(cons) and p.endswith(_TRACE_SUFFIXES)
              and not (set(PurePosixPath(p).parts[:-1]) & _SKIP_PARTS)
              and (not p.endswith(".json") or p[len(cons):].startswith("tests/"))]
    if len(wanted) > 400:
        raise AnalyzeError(f"the consumer folder has {len(wanted)} files; the web demo traces at most 400")

    say("S1", f"S1 detect: fetching {1 + len(protos)} contract file(s) at {base_sha[:7]} and {head_sha[:7]}"
              + (f", {len(migrations)} new migration(s)" if migrations else ""), "info")
    fetches = ([(base_sha, openapi), (head_sha, openapi)] + [(sha, p) for p in protos for sha in (base_sha, head_sha)]
               + [(head_sha, p) for p in migrations] + [(consumer_sha, p) for p in wanted])
    texts = dict(zip(fetches, _parallel(lambda f: gh.raw(repo, f[0], f[1]), fetches)))

    changes: list[dict] = []
    old, new = texts[(base_sha, openapi)], texts[(head_sha, openapi)]
    if old is not None and new is not None:
        changes += _engine("detect.openapi").diff_openapi(old, new)
    for proto in protos:
        old, new = texts[(base_sha, proto)], texts[(head_sha, proto)]
        if old is not None and new is not None:
            changes += _engine("detect.proto").diff_proto_texts(old, new)
    changes += _engine("detect.migrations").diff_migrations(
        [(PurePosixPath(p).name, texts[(head_sha, p)] or "") for p in migrations]
    )
    for surface, label in (("rest", "REST (OpenAPI)"), ("grpc", "gRPC (protobuf)"), ("db", "DB (Alembic)")):
        broken = [c for c in changes if c["surface"] == surface and c["breaking"]]
        if broken:
            say("S1", f"{label}: {len(broken)} breaking - " + ", ".join(
                f"{c['kind']} {c['location']}" for c in broken), "warn")
    n_breaking = [c for c in changes if c["breaking"]]
    say("S1", f"S1 detect: {len(n_breaking)} breaking of {len(changes)} changes (REST "
              f"{sum(c['surface'] == 'rest' for c in n_breaking)}, gRPC {sum(c['surface'] == 'grpc' for c in n_breaking)}, "
              f"DB {sum(c['surface'] == 'db' for c in n_breaking)})", "ok")
    say("S2", f"S2 trace: AST + SQL + proto + fixture scan of {len(wanted)} consumer files in {consumer or 'repo root'}",
        "info")

    tmp = Path(tempfile.mkdtemp(prefix="syncsnitch-"))
    try:
        for p in wanted:
            dest = tmp / p[len(cons):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(texts[(consumer_sha, p)] or "", encoding="utf-8")
        hits = _engine("trace").trace_consumer(changes, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    breaking = [c for c in changes if c["breaking"]]
    return {
        "repo": repo,
        "upstream": upstream,
        "consumer": consumer,
        "base": base, "base_sha": base_sha,
        "head": head, "head_sha": head_sha,
        "consumer_ref": consumer_ref, "consumer_sha": consumer_sha,
        "changes": changes,
        "hits": hits,
        "summary": {
            "total": len(changes),
            "breaking": len(breaking),
            "by_surface": {s: sum(1 for c in breaking if c["surface"] == s) for s in ("rest", "grpc", "db")},
            "files": len({h["file"] for h in hits}),
            "endpoints": sorted({e for h in hits for e in h["endpoints"]}),
        },
        "consumer_files_scanned": len(wanted),
    }


# ---------------------------------------------------------------------------
# S3-S9 status: the Bob run artifact (web/runs/<run_id>.json) and the Actions container run
# ---------------------------------------------------------------------------

def valid_run_id(run_id: str) -> bool:
    return bool(_RUN_ID_RE.match(run_id or ""))


def bob_artifact(gh: GitHub, run_id: str, local_runs: Path) -> dict | None:
    """The run artifact Bob writes at S9: local file first (site running on the laptop), then GitHub."""
    local = local_runs / f"{run_id}.json"
    if local.is_file():
        return json.loads(local.read_text(encoding="utf-8"))
    text = gh.raw(HOME_REPO, RUNS_REF, f"web/runs/{run_id}.json")
    return json.loads(text) if text else None


def actions_inputs(result: dict, run_id: str) -> dict:
    return {
        "repo": result["repo"],
        "upstream": result["upstream"],
        "consumer": result["consumer"],
        "base": result["base_sha"],
        "head": result["head"],
        "consumer_ref": result["consumer_ref"],
        "run_id": run_id,
    }
