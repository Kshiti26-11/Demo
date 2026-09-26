"""Shared fixtures for the website tests: a fake GitHub (no network) serving a fake monorepo."""
from pathlib import Path

import httpx
import pytest

from web.webapp import analyze

ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / "contracts" / "reference"
BILLING = ROOT / "billing-service"
BASE, HEAD = "b" * 40, "h" * 40
MIGRATION = "up/migrations/versions/0002_money_customer_status.py"


def _files(sha: str) -> dict[str, str]:
    """The fake monorepo: up/ = the orders upstream (v1 at BASE, v2 at HEAD), cons/ = billing-service."""
    v = "v1" if sha == BASE else "v2"
    files = {
        "README.md": "# fake monorepo\n",
        "up/pyproject.toml": "[project]\nname = 'up'\n",
        "up/contracts/openapi.yaml": (REFS / v / "openapi.yaml").read_text(),
        "up/contracts/orders.proto": (REFS / v / "orders.proto").read_text(),
        "up/migrations/versions/0001_create_orders.py": (REFS / "migrations" / "0001_create_orders.py").read_text(),
    }
    if sha == HEAD:
        files[MIGRATION] = (REFS / "migrations" / "0002_money_customer_status.py").read_text()
    for p in BILLING.rglob("*"):
        rel = p.relative_to(BILLING).as_posix()
        if p.is_file() and not ({".venv", "__pycache__", ".pytest_cache"} & set(p.parts)) and p.suffix in (
                ".py", ".sql", ".proto", ".json", ".toml", ".yaml"):
            files[f"cons/{rel}"] = p.read_text()
    return files


def fake_github(request: httpx.Request) -> httpx.Response:
    url, path = request.url, request.url.path
    if url.host == "raw.githubusercontent.com":
        _, owner, name, sha, *rest = path.split("/")
        text = _files(sha).get("/".join(rest))
        return httpx.Response(200, text=text) if text is not None else httpx.Response(404)
    routes = {
        "/repos/o/r": {"default_branch": "main", "html_url": "https://github.com/o/r"},
        "/repos/o/r/branches": [{"name": "main"}, {"name": "feat"}],
        f"/repos/o/r/compare/{BASE}...{HEAD}": {"files": [{"filename": MIGRATION, "status": "added"}]},
    }
    if path in routes:
        return httpx.Response(200, json=routes[path])
    if path.startswith("/repos/o/r/git/trees/"):
        ref = path.rsplit("/", 1)[-1]
        paths = ["README.md"] if ref == "main" else list(_files(HEAD))
        return httpx.Response(200, json={"tree": [{"path": p, "type": "blob"} for p in paths]})
    if path == "/repos/o/r/commits":
        return httpx.Response(200, json=[{
            "sha": HEAD, "parents": [{"sha": BASE}],
            "commit": {"message": "feat!: Orders API v2", "committer": {"date": "2026-09-26T00:00:00Z"}},
        }])
    if path.startswith("/repos/o/r/commits/"):
        ref = path.rsplit("/", 1)[-1]
        sha = {"feat": HEAD, "main": BASE}.get(ref, ref)
        return httpx.Response(200, json={"sha": sha}) if sha in (BASE, HEAD) else httpx.Response(404)
    return httpx.Response(404, json={"message": "Not Found"})



@pytest.fixture
def fake_github_client(monkeypatch):
    monkeypatch.setattr(analyze, "client", lambda: analyze.GitHub(None, transport=httpx.MockTransport(fake_github)))
