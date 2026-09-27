"""The cloud runner: the three agents run on GitHub Actions, so the deployed site (Vercel) needs no machine at all.

  site (Vercel)   after S1-S2 dispatches .github/workflows/syncsnitch-agents.yml in RUNNER_REPO (mode agents, publish
                  after the human approves, reject) and shows the run from the branch syncsnitch-live/<run_id> there.
  job (Actions)   `python -m webapp.cloud job ...` runs the same runner as a laptop (agents.py: S2-S9, Docker V3-V5,
                  the draft PR) and force-pushes a snapshot of the run to that branch every few seconds:
                    state.json    exactly what /api/live/<run_id> returns (live.state on the runner)
                    diff.patch    the Transformer's patch
                    artifact.json the S9 run artifact (replay page)
                    run/          the run folder (spec, events, impact, verification, verdict, prompts)
                    fix.bundle    the Transformer's commits, so a later job (publish, resume) can continue the branch
Secrets (repo secrets of RUNNER_REPO, set once by scripts/cloud_setup.sh): an AI engine key such as GEMINI_API_KEY,
and SYNCSNITCH_PUSH_TOKEN for the draft PR in the analyzed repo. Vercel needs GITHUB_TOKEN (Actions: write on
RUNNER_REPO). Locally nothing here is used unless SYNCSNITCH_CLOUD=1.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from . import analyze, live

RUNNER_REPO = os.environ.get("SYNCSNITCH_RUNNER_REPO") or "Cybverse-Pkians/syncsnitch-runner"
RUNNER_REF = os.environ.get("SYNCSNITCH_RUNNER_REF") or "main"
WORKFLOW = "syncsnitch-agents.yml"
MODES = ("agents", "publish", "reject")
ACTIVE_RUN = ("queued", "in_progress", "waiting", "requested", "pending")
POLL_MS = 3000  # the page polls a cloud run every 3 s (GitHub API budget)
SNAPSHOT_EVERY = 3.0
SETUP_FIX = "bash scripts/cloud_setup.sh   (once, on any laptop with the repo and gh logged in)"

_CACHE: dict[str, tuple[float, str | None, object]] = {}  # url -> (fetched_at, etag, value)
_CACHE_LOCK = threading.Lock()
_PENDING: dict[str, tuple[str, float]] = {}  # run_id -> (mode, monotonic time) of a dispatch from this instance
_GH: list = []


class CloudError(Exception):
    """A cloud action that cannot be done now; the message is shown on the page."""


def enabled() -> bool:
    """The deployed site (Vercel) runs the agents in the cloud; SYNCSNITCH_CLOUD=1 does the same anywhere."""
    return live.ON_VERCEL or os.environ.get("SYNCSNITCH_CLOUD") == "1"


def branch(run_id: str) -> str:
    return f"syncsnitch-live/{run_id}"


def reset() -> None:
    """Forget cached GitHub answers (tests)."""
    _CACHE.clear()
    _PENDING.clear()
    _GH.clear()


def _gh() -> analyze.GitHub:
    """One GitHub client per process (tests swap analyze.client, which starts a new one)."""
    if not _GH or _GH[0][0] is not analyze.client:
        _GH[:] = [(analyze.client, analyze.client())]
    return _GH[0][1]


def _fetch(url: str, ttl: float, raw: bool = False):
    """GET with a short per-instance cache and ETags (a 304 does not count against the GitHub rate limit)."""
    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(url)
    if hit and now - hit[0] < ttl:
        return hit[2]
    headers = {"Accept": "application/vnd.github.raw+json"} if raw else {}
    if hit and hit[1]:
        headers["If-None-Match"] = hit[1]
    try:
        r = _gh().http.get(url, headers=headers)
    except httpx.HTTPError:
        return hit[2] if hit else None
    if r.status_code == 304 and hit:
        value, etag = hit[2], hit[1]
    elif r.status_code == 200:
        try:
            value = r.text if raw else r.json()
        except ValueError:
            value = None
        etag = r.headers.get("ETag")
    elif r.status_code == 404:
        value, etag = None, None
    else:  # rate limit or a GitHub hiccup: keep showing the last answer
        return hit[2] if hit else None
    with _CACHE_LOCK:
        _CACHE[url] = (now, etag, value)
    return value


def remote_file(run_id: str, name: str, ttl: float = 2.0) -> str | None:
    if not analyze.valid_run_id(run_id):
        return None
    url = (f"{analyze.API}/repos/{RUNNER_REPO}/contents/{name}?ref={quote(branch(run_id), safe='')}")
    value = _fetch(url, ttl, raw=True)
    return value if isinstance(value, str) else None


def live_run_ids(ttl: float = 30.0) -> list[str]:
    """Every run the cloud runner has a live branch for (syncsnitch-live/<run_id>), newest first."""
    refs = _fetch(f"{analyze.API}/repos/{RUNNER_REPO}/git/matching-refs/heads/syncsnitch-live/", ttl)
    ids = [str(r.get("ref", "")).rsplit("/", 1)[-1] for r in refs or [] if isinstance(r, dict)]
    return sorted((i for i in ids if analyze.valid_run_id(i)), reverse=True)


def remote_state(run_id: str, ttl: float = 2.0) -> dict | None:
    text = remote_file(run_id, "state.json", ttl)
    try:
        data = json.loads(text) if text else None
    except ValueError:
        return None
    return data if isinstance(data, dict) and data.get("run_id") == run_id else None


def artifact(run_id: str) -> dict | None:
    text = remote_file(run_id, "artifact.json", ttl=30)
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def diff(run_id: str) -> str | None:
    return remote_file(run_id, "diff.patch", ttl=3)


def runs(run_id: str, ttl: float = 8.0) -> list[dict]:
    """This run's GitHub Actions jobs, newest first (run-name: 'syncsnitch-agents <mode> <run_id>')."""
    data = _fetch(f"{analyze.API}/repos/{RUNNER_REPO}/actions/workflows/{WORKFLOW}/runs?per_page=50", ttl)
    out = []
    for r in (data or {}).get("workflow_runs", []) if isinstance(data, dict) else []:
        words = str(r.get("display_title") or "").split()
        if len(words) == 3 and words[0] == "syncsnitch-agents" and words[2] == run_id:
            out.append({"id": r.get("id"), "mode": words[1], "status": r.get("status"),
                        "conclusion": r.get("conclusion"), "html_url": r.get("html_url"),
                        "created_at": r.get("created_at") or ""})
    return sorted(out, key=lambda r: r["created_at"], reverse=True)


# ---------------------------------------------------------------------------
# Site side: status, dispatch, the state the page shows
# ---------------------------------------------------------------------------

def status() -> dict:
    """agents.runner_status() on the deployed site: can it start the cloud runner?"""
    base = {"where": "cloud", "backend": "cloud", "label": "GitHub Actions", "model": None, "unit": "tokens",
            "docker": True, "budget": None, "runner_repo": RUNNER_REPO}
    if not _gh().has_token:
        return {**base, "ready": False, "problems": [{
            "id": "cloud", "text": f"The 3 agents run on GitHub Actions ({RUNNER_REPO}), with no machine of yours. "
                                   "This deployment has no GitHub token to start them.",
            "fix": f"Vercel → Settings → Environment Variables: GITHUB_TOKEN = a token with Actions: write on "
                   f"{RUNNER_REPO}, then Redeploy"}]}
    if _fetch(f"{analyze.API}/repos/{RUNNER_REPO}", ttl=300) is None:
        return {**base, "ready": False, "problems": [{
            "id": "cloud", "text": f"The cloud runner repo {RUNNER_REPO} was not found, or this deployment's "
                                   "GITHUB_TOKEN cannot see it.", "fix": SETUP_FIX}]}
    return {**base, "ready": True, "problems": []}


def dispatch(run_id: str, mode: str, spec: dict | None = None) -> None:
    if mode not in MODES or not analyze.valid_run_id(run_id):
        raise CloudError("bad cloud action")
    spec = spec or {}
    inputs = {"run_id": run_id, "mode": mode, "link": spec.get("link") or "",
              "upstream": spec.get("upstream") or "", "consumer": spec.get("consumer") or "",
              "base": spec.get("base_sha") or spec.get("base") or "", "head": spec.get("head") or "",
              "site_url": spec.get("site_url") or ""}
    try:
        r = _gh().http.post(f"{analyze.API}/repos/{RUNNER_REPO}/actions/workflows/{WORKFLOW}/dispatches",
                            json={"ref": RUNNER_REF, "inputs": inputs})
    except httpx.HTTPError as e:
        raise CloudError(f"could not reach GitHub to start the cloud runner: {e}") from e
    if r.status_code == 404:
        raise CloudError(f"the cloud runner {RUNNER_REPO} has no {WORKFLOW}, or GITHUB_TOKEN cannot see it "
                         f"(fix: {SETUP_FIX})")
    if r.status_code in (401, 403):
        raise CloudError(f"GITHUB_TOKEN may not start workflows in {RUNNER_REPO} (it needs Actions: write)")
    if r.status_code != 204:
        raise CloudError(f"GitHub refused to start the cloud runner ({r.status_code}): {r.text[:200]}")
    _PENDING[run_id] = (mode, time.monotonic())
    with _CACHE_LOCK:  # the next poll must see the new job
        _CACHE.pop(f"{analyze.API}/repos/{RUNNER_REPO}/actions/workflows/{WORKFLOW}/runs?per_page=50", None)


def start_new(run_id: str, spec: dict) -> bool:
    """Right after the site's S1-S2: hand S3-S9 to the cloud runner."""
    st = status()
    if not st["ready"]:
        spec["cloud_error"] = st["problems"][0]["text"]
        live._save_spec(run_id, spec)
        live.emit(run_id, "S2", "site", f"Cannot start the agents: {st['problems'][0]['text']} "
                                        f"Fix: {st['problems'][0]['fix']}", "error")
        return False
    try:
        dispatch(run_id, "agents", spec)
    except CloudError as e:
        spec["cloud_error"] = str(e)
        live._save_spec(run_id, spec)
        live.emit(run_id, "S2", "site", f"Could not start the cloud runner: {e}", "error")
        return False
    live.emit(run_id, "S2", "site", f"S1-S2 done: the 3 agents start on GitHub Actions ({RUNNER_REPO}), no machine "
                                    "needed - Tracer -> Transformer -> Verifier, Docker V3-V5, then your approval",
              "ok")
    return True


def act(run_id: str, mode: str) -> None:
    """Start / resume (agents), Approve (publish) or Reject from the run page."""
    st = live_state(run_id, lambda: _local_state(run_id))
    r = (st or {}).get("runner") or {}
    if st is None:
        raise CloudError("run not found")
    allowed = {"agents": r.get("can_start"), "publish": r.get("can_approve"), "reject": r.get("can_reject")}[mode]
    if not allowed:
        raise CloudError({"agents": "the agents are already running or this run is past them",
                          "publish": "this run is not waiting for approval with a green verdict",
                          "reject": "this run is not waiting for approval"}[mode])
    spec = live._load(live._run_dir(run_id) / "spec.json") or {}
    if mode == "agents" and not st.get("cloud") and not spec.get("base_sha"):
        raise CloudError("reload the page and try again (this server has not traced the run yet)")
    dispatch(run_id, mode, spec)


def _local_state(run_id: str) -> dict | None:
    try:
        return live.state(run_id)
    except analyze.AnalyzeError:
        return None


def _runner(**over) -> dict:
    view = {"state": "preparing", "backend": "cloud", "label": "GitHub Actions", "model": None, "unit": "tokens",
            "budget": None, "spent": 0, "spent_by": {}, "tasks": {}, "docker": True, "error": None, "verdict": None,
            "problems": [], "can_approve": False, "can_reject": False, "can_start": False}
    view.update(over)
    return view


def _optimistic(st: dict, mode: str) -> None:
    """A job was just dispatched and has not reported yet: show what it is doing."""
    r = st.get("runner") or _runner()
    r.update(error=None, can_start=False, can_approve=False, can_reject=False, problems=[])
    st["spec"]["error"] = None
    if mode == "agents":
        st["phase"], r["state"] = "active", "preparing"
        if st["tracer"].get("status") in ("waiting", "waiting_bob", "failed", "stopped"):
            st["tracer"]["status"] = "running"
    elif mode == "publish":
        st["phase"], r["state"] = "publishing", "publishing"
    else:
        st["phase"], r["state"] = "aborted", "rejected"
    st["runner"] = r


def _interrupted(st: dict, job: dict) -> None:
    """The job ended while the run was still going (cancelled, timed out, runner lost)."""
    r = st.get("runner") or _runner()
    msg = (f"The GitHub Actions job stopped ({job.get('conclusion') or job.get('status')}) before this step finished. "
           f"Log: {job.get('html_url')}.")
    if st["phase"] == "publishing":
        st["phase"] = "approval"
        r.update(state="publish_failed", error=msg + " Press Approve again to retry.",
                 can_approve=st["verifier"].get("verdict") == "green", can_reject=True)
    else:
        st["phase"] = "interrupted"
        r.update(state="interrupted", error=msg + " Resume continues from the last finished step.", can_start=True)
    st["runner"] = r


def live_state(run_id: str, local) -> dict | None:
    """What /api/live returns on the deployed site: the runner's snapshot, reconciled with its GitHub Actions jobs.
    `local` returns the site's own S0-S2 state (used until the runner has pushed its first snapshot)."""
    remote = remote_state(run_id)
    st = remote if remote is not None else local()
    if st is None:
        return None
    jobs = runs(run_id)
    latest = jobs[0] if jobs else None
    active = bool(latest and latest["status"] in ACTIVE_RUN)
    pending = _PENDING.get(run_id)
    pending = pending if pending and time.monotonic() - pending[1] < 120 else None
    snap = st.get("cloud") or {}
    if remote is not None:
        current = latest and str(latest["id"]) == str(snap.get("job"))
        if active and not current:
            _optimistic(st, latest["mode"])
        elif latest and not active and current and st["phase"] in ("active", "publishing", "tracing"):
            _interrupted(st, latest)
        elif latest and not active and not current and latest["created_at"] > str(snap.get("snapshot_at") or "") \
                and latest["conclusion"] != "success":
            _interrupted(st, latest)
        elif pending and not active and not (latest and latest["created_at"] > str(snap.get("snapshot_at") or "")):
            _optimistic(st, pending[0])
        r = st.get("runner")
        if r and st["phase"] in ("failed", "interrupted") and not active:
            r["can_start"] = True
    elif st["phase"] in ("waiting_bob", "blocked"):
        spec = live._load(live._run_dir(run_id) / "spec.json") or {}
        traced = str(spec.get("traced_at") or "")
        fresh = bool(traced) and traced >= datetime.fromtimestamp(time.time() - 60, tz=timezone.utc).isoformat()
        if active or pending or (fresh and not latest and not spec.get("cloud_error")):
            st["runner"] = _runner()
            _optimistic(st, latest["mode"] if active else pending[0] if pending else "agents")
        elif latest:
            st["runner"] = _runner()
            st["phase"] = "interrupted"
            _interrupted(st, latest)
        else:
            s = status()
            problems = s["problems"] or [{"id": "cloud-start", "text": spec.get("cloud_error") or
                                          "The agents have not started for this case yet: press Start to run them "
                                          f"on GitHub Actions ({RUNNER_REPO}).", "fix": ""}]
            st["phase"] = "blocked"
            st["runner"] = _runner(state="blocked", problems=problems, can_start=s["ready"])
    if latest:
        st["actions"] = {"status": latest["status"], "conclusion": latest["conclusion"],
                         "html_url": latest["html_url"]}
        keys = {e.get("key") for e in st.get("events", [])}
        for j in reversed(jobs[:5]):
            key = f"cloud-{j['id']}"
            if key not in keys:
                st.setdefault("events", []).append({
                    "key": key, "ts": j["created_at"].replace("Z", ".000+00:00"), "step": "S2", "agent": "site",
                    "level": "info", "msg": f"GitHub Actions job ({j['mode']}): {j['html_url']}"})
        st["events"].sort(key=lambda e: e["ts"])
    st["poll_ms"] = POLL_MS
    return st


# ---------------------------------------------------------------------------
# Job side (GitHub Actions): run the local runner and push snapshots
# ---------------------------------------------------------------------------

def _job_repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY") or RUNNER_REPO


def _remote_url() -> str:
    return os.environ.get("SYNCSNITCH_LIVE_REMOTE") or f"https://github.com/{_job_repo()}.git"  # override: tests


def _git(*args: str, cwd: Path | None = None, env: dict | None = None, timeout: int = 120) -> tuple[int, str]:
    try:
        out = subprocess.run(["git", *args], cwd=str(cwd or live.REPO_ROOT), capture_output=True, text=True,
                             timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _say(msg: str) -> None:
    print(f"[syncsnitch-cloud] {msg}", flush=True)


def restore(run_id: str) -> bool:
    """Bring back a run's folder, artifact and fix branch from its live branch (resume, publish, reject)."""
    ref = f"refs/remotes/syncsnitch-live/{run_id}"
    code, out = _git("fetch", "--quiet", "--force", _remote_url(), f"+refs/heads/{branch(run_id)}:{ref}", timeout=180)
    if code != 0:
        _say(f"no earlier snapshot of {run_id} ({out.strip()[:200]})")
        return False
    data = subprocess.run(["git", "archive", "--format=tar", ref], cwd=str(live.REPO_ROOT), capture_output=True,
                          timeout=120).stdout
    tmp = Path(tempfile.mkdtemp(prefix="syncsnitch-restore-"))
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(tmp, filter="data")
    run_dir = live._run_dir(run_id)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    if (tmp / "run").is_dir():
        shutil.copytree(tmp / "run", run_dir)
    if (tmp / "artifact.json").is_file():
        live.WEB_RUNS.mkdir(parents=True, exist_ok=True)
        shutil.copy(tmp / "artifact.json", live.WEB_RUNS / f"{run_id}.json")
    spec = live._load(run_dir / "spec.json") or {}
    bundle = tmp / "fix.bundle"
    if spec.get("repo") and bundle.is_file():
        from . import agents  # noqa: PLC0415

        work = live.WORK_DIR / run_id
        if work.exists():
            shutil.rmtree(work)
        work.parent.mkdir(parents=True, exist_ok=True)
        code, out = agents._run(agents._clone_cmd(spec["repo"], work), timeout=600)
        if code != 0:
            raise CloudError(f"could not clone {spec['repo']}: {out.strip()[-300:]}")
        b = f"syncsnitch/{run_id}"
        code, out = _git("-C", str(work), "fetch", "--quiet", str(bundle), f"+refs/heads/{b}:refs/heads/{b}")
        if code != 0:
            raise CloudError(f"could not restore {b} from the snapshot: {out.strip()[-300:]}")
        _git("-C", str(work), "checkout", "--quiet", b)
    _say(f"restored {run_id} from {branch(run_id)} (state {((spec.get('runner') or {}).get('state'))})")
    return bool(spec)


class Snapshots(threading.Thread):
    """Force-pushes the run's snapshot to syncsnitch-live/<run_id> whenever it changes (every 3 s at most)."""

    def __init__(self, run_id: str, mode: str):
        super().__init__(daemon=True, name=f"snapshots-{run_id}")
        self.run_id, self.mode = run_id, mode
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.digest = None
        self.stage_root = Path(tempfile.mkdtemp(prefix="syncsnitch-live-"))
        self.job = os.environ.get("GITHUB_RUN_ID") or f"local-{os.getpid()}"
        server = os.environ.get("GITHUB_SERVER_URL") or "https://github.com"
        self.url = f"{server}/{_job_repo()}/actions/runs/{self.job}"

    def run(self) -> None:
        while not self.done.wait(SNAPSHOT_EVERY):
            try:
                self.push()
            except Exception as e:  # noqa: BLE001 - a failed snapshot must not stop the run
                _say(f"snapshot failed: {type(e).__name__}: {e}")

    def stop(self) -> None:
        self.done.set()
        self.join(timeout=30)
        for _ in range(3):
            try:
                self.push()
                return
            except Exception as e:  # noqa: BLE001
                _say(f"final snapshot failed: {type(e).__name__}: {e}")
                time.sleep(3)

    def _state(self) -> dict | None:
        st = live.state(self.run_id)
        if st is None:
            return None
        r = st.get("runner") or {}
        if r.get("state") == "blocked":  # the laptop fixes do not apply here: the runner's secrets are missing
            r["problems"] = [{"id": p.get("id"), "text": p.get("text", "").replace("on this machine", "")
                              + f" (GitHub Actions secrets of {_job_repo()})", "fix": SETUP_FIX}
                             for p in r.get("problems") or []]
            r["can_start"] = True
        err = str(r.get("error") or "")
        if r.get("state") == "publish_failed" and any(w in err for w in ("403", "denied", "Permission")):
            r["error"] = err + f" (the runner needs SYNCSNITCH_PUSH_TOKEN with push access: {SETUP_FIX})"
        return st

    def push(self) -> None:
        with self.lock:
            st = self._state()
            if st is None:
                return
            stage = self.stage_root / "stage"
            if stage.exists():
                shutil.rmtree(stage)
            stage.mkdir(parents=True)
            run_dir = live._run_dir(self.run_id)
            if run_dir.is_dir():
                shutil.copytree(run_dir, stage / "run",
                                ignore=lambda d, names: [n for n in names if (Path(d) / n).is_file()
                                                         and (Path(d) / n).stat().st_size > 5_000_000])
            (stage / "diff.patch").write_text(live.diff_text(self.run_id), encoding="utf-8")
            art = live.WEB_RUNS / f"{self.run_id}.json"
            if art.is_file():
                shutil.copy(art, stage / "artifact.json")
            self._bundle(stage)
            body = json.dumps(st, sort_keys=True)
            h = hashlib.sha256(body.encode())
            for f in sorted(stage.rglob("*")):
                if f.is_file():
                    h.update(f.relative_to(stage).as_posix().encode())
                    h.update(f.read_bytes())
            digest = h.hexdigest()
            if digest == self.digest:
                return
            st["cloud"] = {"job": self.job, "mode": self.mode, "html_url": self.url, "runner_repo": _job_repo(),
                           "snapshot_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
                           .replace("+00:00", "Z")}
            (stage / "state.json").write_text(json.dumps(st, indent=1), encoding="utf-8")
            self._commit_push(stage)
            self.digest = digest

    def _bundle(self, stage: Path) -> None:
        work = live.WORK_DIR / self.run_id
        spec = live._load(live._run_dir(self.run_id) / "spec.json") or {}
        b, head = f"syncsnitch/{self.run_id}", spec.get("head_sha")
        if not head or not (work / ".git").exists():
            return
        code, ahead = _git("-C", str(work), "rev-list", "--count", f"{head}..{b}")
        if code != 0 or not ahead.strip().isdigit() or int(ahead.strip()) == 0:
            return
        code, out = _git("-C", str(work), "bundle", "create", "--quiet", str(stage / "fix.bundle"), b, f"^{head}")
        if code != 0:
            _say(f"could not bundle {b}: {out.strip()[:200]}")

    def _commit_push(self, stage: Path) -> None:
        index = self.stage_root / "index"
        index.unlink(missing_ok=True)
        who = {"GIT_AUTHOR_NAME": "SyncSnitch runner", "GIT_AUTHOR_EMAIL": "syncsnitch-runner@users.noreply.github.com"}
        env = {**os.environ, "GIT_INDEX_FILE": str(index), **who,
               "GIT_COMMITTER_NAME": who["GIT_AUTHOR_NAME"], "GIT_COMMITTER_EMAIL": who["GIT_AUTHOR_EMAIL"]}
        git_dir = str(live.REPO_ROOT / ".git")
        code, out = _git("--git-dir", git_dir, "--work-tree", str(stage), "add", "-A", "-f", ".", env=env)
        if code != 0:
            raise CloudError(f"git add: {out.strip()[:200]}")
        code, tree = _git("--git-dir", git_dir, "write-tree", env=env)
        if code != 0:
            raise CloudError(f"git write-tree: {tree.strip()[:200]}")
        code, commit = _git("--git-dir", git_dir, "commit-tree", tree.strip(), "-m",
                            f"SyncSnitch live snapshot {self.run_id} ({self.mode})", env=env)
        if code != 0:
            raise CloudError(f"git commit-tree: {commit.strip()[:200]}")
        code, out = _git("--git-dir", git_dir, "push", "--quiet", "--force", _remote_url(),
                         f"{commit.strip()}:refs/heads/{branch(self.run_id)}", timeout=120)
        if code != 0:
            raise CloudError(f"git push: {out.strip()[:300]}")


def job(mode: str, run_id: str, link: str = "", upstream: str = "", consumer: str = "", base: str = "",
        head: str = "", site_url: str = "") -> int:
    """One GitHub Actions job: S0-S2 + the agents (mode agents), S8-S9 (publish) or the rejection (reject)."""
    from . import agents  # noqa: PLC0415

    if mode not in MODES or not analyze.valid_run_id(run_id):
        _say("bad mode or run id")
        return 2
    restored = restore(run_id)
    snaps = Snapshots(run_id, mode)
    snaps.start()
    try:
        if mode == "agents":
            if restored:
                if not agents.start(run_id):
                    _say(f"nothing to resume: {(live._load(live._run_dir(run_id) / 'spec.json') or {}).get('runner')}")
            else:
                if not link:
                    raise CloudError("no repo link to start from")
                overrides = {"upstream": upstream, "consumer": consumer, **({"base": base} if base else {}),
                             **({"head": head} if head else {})}
                live.launch(link, site_url or "https://syncsnitch.vercel.app", overrides, run_id=run_id,
                            background=False)
        elif not restored:
            raise CloudError("this run has no snapshot to continue from")
        elif mode == "publish":
            agents.approve(run_id)
        else:
            agents.reject(run_id)
        while agents.is_running(run_id):
            time.sleep(2)
    except (CloudError, agents.StageError, analyze.AnalyzeError) as e:
        _say(f"stopped: {e}")
        if (live._run_dir(run_id) / "spec.json").exists():
            live.emit(run_id, "S2", "site", f"Cloud runner: {e}", "error")
    finally:
        snaps.stop()
    spec = live._load(live._run_dir(run_id) / "spec.json") or {}
    state = (spec.get("runner") or {}).get("state")
    _say(f"run {run_id}: status {spec.get('status')}, runner {state}")
    ok = state in ("approval", "complete", "rejected") or (spec.get("summary") or {}).get("breaking") == 0
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m webapp.cloud", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("job", help="run one cloud runner job (GitHub Actions)")
    j.add_argument("--mode", choices=MODES, required=True)
    j.add_argument("--run-id", required=True)
    for name in ("link", "upstream", "consumer", "base", "head", "site-url"):
        j.add_argument(f"--{name}", default="")
    a = p.parse_args(argv)
    return job(a.mode, a.run_id, a.link, a.upstream, a.consumer, a.base, a.head, a.site_url)


if __name__ == "__main__":
    sys.exit(main())
