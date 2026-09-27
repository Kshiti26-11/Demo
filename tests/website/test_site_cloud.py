"""The cloud runner (web/webapp/cloud.py): on Vercel the site hands S3-S9 to GitHub Actions and shows the run from the
job's live branch; the job pushes snapshots there and a later job (publish, resume) restores them."""
import json
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from web.webapp import analyze, cloud, live
from web.webapp.main import app

from conftest import fake_github  # noqa: E402

RUNNER = "me/runner"


class FakeRunner:
    """GitHub for the runner repo: workflow dispatches, the job list and the live branch's files."""

    def __init__(self):
        self.dispatched: list[dict] = []
        self.jobs: list[dict] = []
        self.files: dict[str, str] = {}  # "<run_id>/<name>" -> text

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == f"/repos/{RUNNER}":
            return httpx.Response(200, json={"full_name": RUNNER})
        if path == f"/repos/{RUNNER}/actions/workflows/{cloud.WORKFLOW}/dispatches":
            inputs = json.loads(request.content)["inputs"]
            self.dispatched.append(inputs)
            self.jobs.insert(0, {"id": len(self.jobs) + 1, "status": "queued", "conclusion": None,
                                 "html_url": f"https://github.com/{RUNNER}/actions/runs/{len(self.jobs) + 1}",
                                 "created_at": f"2099-01-01T00:00:0{len(self.jobs)}Z",
                                 "display_title": f"syncsnitch-agents {inputs['mode']} {inputs['run_id']}"})
            return httpx.Response(204)
        if path == f"/repos/{RUNNER}/actions/workflows/{cloud.WORKFLOW}/runs":
            return httpx.Response(200, json={"workflow_runs": self.jobs})
        if path.startswith(f"/repos/{RUNNER}/contents/"):
            run_id = request.url.params["ref"].removeprefix("syncsnitch-live/")
            text = self.files.get(f"{run_id}/{path.rsplit('/', 1)[-1]}")
            return httpx.Response(200, text=text) if text is not None else httpx.Response(404)
        return fake_github(request)


@pytest.fixture
def runner(monkeypatch, tmp_path):
    fake = FakeRunner()
    monkeypatch.setattr(analyze, "client", lambda: analyze.GitHub("t", transport=httpx.MockTransport(fake)))
    monkeypatch.setattr(cloud, "RUNNER_REPO", RUNNER)
    monkeypatch.setattr(live, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(live, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(live, "WEB_RUNS", tmp_path / "web-runs")
    monkeypatch.setattr(live, "ON_VERCEL", True)
    cloud.reset()
    yield fake
    cloud.reset()


def launch(client) -> str:
    r = client.post("/api/launch", json={"link": "https://github.com/o/r"})
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


def state(client, run_id: str) -> dict:
    r = client.get(f"/api/live/{run_id}")
    assert r.status_code == 200, r.text
    return r.json()


def snapshot(run_id: str, phase: str, runner_state: str, job: int, verdict=None, **runner) -> str:
    return json.dumps({
        "run_id": run_id, "phase": phase, "spec": {"repo": "o/r", "link": "https://github.com/o/r", "error": None},
        "tracer": {"status": "done", "endpoints": []}, "transformer": {"status": "done", "branch": "b"},
        "verifier": {"status": "done", "verdict": verdict, "checks": []},
        "runner": {"state": runner_state, "can_start": False, "can_approve": verdict == "green",
                   "can_reject": runner_state == "approval", "error": None, **runner},
        "events": [{"key": "e0", "ts": "2099-01-01T00:00:10.000+00:00", "step": "S3", "agent": "tracer",
                    "level": "ok", "msg": "Tracer done"}],
        "cloud": {"job": str(job), "mode": "agents", "snapshot_at": "2099-01-01T00:00:30Z"}})


def test_launch_on_vercel_dispatches_the_cloud_runner(runner):
    client = TestClient(app)
    run_id = launch(client)
    assert runner.dispatched == [{"run_id": run_id, "mode": "agents", "link": "https://github.com/o/r",
                                  "upstream": "up", "consumer": "cons", "base": "b" * 40, "head": "feat",
                                  "site_url": "http://testserver"}]
    s = state(client, run_id)  # the job has not pushed a snapshot yet: queued, with a link to the job
    assert s["phase"] == "active" and s["runner"]["state"] == "preparing" and s["runner"]["label"] == "GitHub Actions"
    assert s["tracer"]["status"] == "running" and s["poll_ms"] == cloud.POLL_MS
    assert s["actions"]["html_url"].endswith("/actions/runs/1")
    assert any("GitHub Actions job (agents)" in e["msg"] for e in s["events"])
    assert any("start on GitHub Actions" in e["msg"] for e in s["events"])


def test_the_page_shows_the_runner_snapshot_then_approve_dispatches_publish(runner):
    client = TestClient(app)
    run_id = launch(client)
    runner.jobs[0].update(status="completed", conclusion="success")
    runner.files[f"{run_id}/state.json"] = snapshot(run_id, "approval", "approval", 1, "green")
    runner.files[f"{run_id}/diff.patch"] = "diff --git a/x b/x\n+new\n"
    cloud.reset()
    s = state(client, run_id)
    assert s["phase"] == "approval" and s["runner"]["can_approve"] and s["verifier"]["verdict"] == "green"
    assert client.get(f"/api/live/{run_id}/diff").json()["diff"].startswith("diff --git")
    r = client.post(f"/api/live/{run_id}/approve")
    assert r.status_code == 200, r.text
    assert runner.dispatched[-1]["mode"] == "publish" and runner.dispatched[-1]["run_id"] == run_id
    assert state(client, run_id)["phase"] == "publishing"  # until the publish job pushes its snapshot
    assert client.post(f"/api/live/{run_id}/approve").status_code == 409  # no second publish job


def test_a_job_that_died_mid_run_can_be_resumed(runner):
    client = TestClient(app)
    run_id = launch(client)
    runner.jobs[0].update(status="completed", conclusion="cancelled")
    runner.files[f"{run_id}/state.json"] = snapshot(run_id, "active", "transformer", 1)
    cloud.reset()
    s = state(client, run_id)
    assert s["phase"] == "interrupted" and s["runner"]["can_start"] and "cancelled" in s["runner"]["error"]
    assert client.post(f"/api/live/{run_id}/agents").status_code == 200
    assert runner.dispatched[-1]["mode"] == "agents"


def test_a_fresh_instance_shows_a_cloud_run_without_retracing(runner, monkeypatch):
    run_id = "w-20990101-000000-abcd"
    runner.jobs.append({"id": 7, "status": "in_progress", "conclusion": None, "html_url": "https://x/7",
                        "created_at": "2099-01-01T00:00:00Z", "display_title": f"syncsnitch-agents agents {run_id}"})
    runner.files[f"{run_id}/state.json"] = snapshot(run_id, "active", "tracer", 7)
    monkeypatch.setattr(live, "ensure", lambda *a, **k: pytest.fail("must not rebuild S0-S2"))
    client = TestClient(app)
    assert client.get(f"/live/{run_id}").status_code == 200
    s = state(client, run_id)
    assert s["phase"] == "active" and "Tracer done" in [e["msg"] for e in s["events"]]


def test_without_a_token_the_page_says_what_to_set(monkeypatch, tmp_path, fake_github_client):
    monkeypatch.setattr(live, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(live, "ON_VERCEL", True)
    cloud.reset()
    client = TestClient(app)
    run_id = launch(client)
    s = state(client, run_id)
    assert s["phase"] == "blocked" and s["runner"]["problems"][0]["id"] == "cloud"
    assert "GITHUB_TOKEN" in s["runner"]["problems"][0]["fix"] and not s["runner"]["can_start"]


# --- job side ----------------------------------------------------------------------------------------------------

def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def test_snapshots_push_to_the_live_branch_and_restore_brings_the_run_back(tmp_path, monkeypatch):
    remote = tmp_path / "runner.git"
    _git(tmp_path, "init", "--bare", "-q", str(remote))
    root = tmp_path / "code"
    root.mkdir()
    _git(root, "init", "-q")
    run_id = "w-20990101-000000-abcd"
    monkeypatch.setattr(live, "REPO_ROOT", root)
    monkeypatch.setattr(live, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(live, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(live, "WEB_RUNS", tmp_path / "web-runs")
    monkeypatch.setattr(cloud, "_remote_url", lambda: str(remote))
    monkeypatch.setattr(live, "state", lambda rid: {"run_id": rid, "phase": "approval",
                                                     "runner": {"state": "approval"}, "events": []})
    monkeypatch.setattr(live, "diff_text", lambda rid: "+patch\n")
    run_dir = live.RUNS_DIR / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "spec.json").write_text(json.dumps({"run_id": run_id, "status": "traced",
                                                   "runner": {"state": "approval"}}))
    (run_dir / "impact.json").write_text("{}")
    snaps = cloud.Snapshots(run_id, "agents")
    snaps.push()
    tree = _git(remote, "ls-tree", "-r", "--name-only", f"syncsnitch-live/{run_id}").split()
    assert set(tree) == {"state.json", "diff.patch", "run/spec.json", "run/impact.json"}
    pushed = json.loads(_git(remote, "show", f"syncsnitch-live/{run_id}:state.json"))
    assert pushed["phase"] == "approval" and pushed["cloud"]["mode"] == "agents"
    first = _git(remote, "rev-parse", f"syncsnitch-live/{run_id}")
    snaps.push()  # nothing changed: no new push
    assert _git(remote, "rev-parse", f"syncsnitch-live/{run_id}") == first

    import shutil
    shutil.rmtree(live.RUNS_DIR)
    assert cloud.restore(run_id) is True  # a later job (publish, resume) starts from the snapshot
    assert json.loads((run_dir / "spec.json").read_text())["runner"]["state"] == "approval"
    assert (run_dir / "impact.json").exists()
