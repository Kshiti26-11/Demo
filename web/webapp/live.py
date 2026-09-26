"""Live multi-agent runs: "Run 3 Agents" -> /live/<run_id>.

Nothing here is simulated. The page shows only:
  - the website's own S1 detect + S2 trace (the vendored SyncSnitch engine on the GitHub API),
  - events.jsonl lines written by the `syncsnitch` CLI, the local agent runner (agents.py: IBM Bob Shell or Claude)
    and `syncsnitch log` (agents started by hand in the Bob IDE),
  - facts read from the run's files (impact.json, verification.json, verdict.json, web/runs/<id>.json) and from
    git in Bob's work clone (.syncsnitch/work/<run_id>, branch syncsnitch/<run_id>).
Locally the run folder is the repo's .syncsnitch/runs, the same folder IBM Bob writes to, so the page follows Bob live.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from . import analyze

REPO_ROOT = Path(__file__).resolve().parents[2]
ON_VERCEL = bool(os.environ.get("VERCEL"))
RUNS_DIR = Path(os.environ.get("SYNCSNITCH_RUNS_DIR")
                or ("/tmp/syncsnitch/runs" if ON_VERCEL else REPO_ROOT / ".syncsnitch" / "runs"))
WORK_DIR = Path(os.environ.get("SYNCSNITCH_WORK_DIR") or REPO_ROOT / ".syncsnitch" / "work")
WEB_RUNS = Path(os.environ.get("SYNCSNITCH_WEB_RUNS") or REPO_ROOT / "web" / "runs")
_FOLDER_RE = re.compile(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$|^$")
_REF_RE = re.compile(r"^[A-Za-z0-9_./-]{1,200}$")
_LOCK = threading.Lock()
_ACTIONS_CACHE: dict[str, tuple[float, dict | None]] = {}


def _engine_events():
    analyze.load("syncsnitch_engine")
    import importlib  # noqa: PLC0415

    return importlib.import_module("syncsnitch_engine.events")


def emit(run_id: str, step: str, agent: str, msg: str, level: str = "info") -> None:
    _engine_events().emit(RUNS_DIR, run_id, step, agent, msg, level)


def _run_dir(run_id: str) -> Path:
    if not analyze.valid_run_id(run_id):
        raise analyze.AnalyzeError("bad run id")
    return RUNS_DIR / run_id


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError):
        return None


def _save_spec(run_id: str, spec: dict) -> None:
    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        (run_dir / "spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")


def validate_overrides(o: dict) -> dict:
    clean = {}
    for key in ("upstream", "consumer"):
        if o.get(key) is not None:
            if not _FOLDER_RE.match(o[key]) or ".." in o[key]:
                raise analyze.AnalyzeError(f"bad {key} folder")
            clean[key] = o[key]
    for key in ("base", "head"):
        if o.get(key):
            if not _REF_RE.match(o[key]) or ".." in o[key]:
                raise analyze.AnalyzeError(f"bad {key} ref")
            clean[key] = o[key]
    return clean


# ---------------------------------------------------------------------------
# Launch: S0 resolve + S1 detect + S2 trace on the website
# ---------------------------------------------------------------------------

def launch(link: str, site_url: str, overrides: dict | None = None, run_id: str | None = None,
           background: bool | None = None) -> str:
    link = (link or "").strip()
    parsed = analyze.parse_repo_url(link)  # fail fast on a bad link, before anything is created
    overrides = validate_overrides(overrides or {})
    run_id = run_id if run_id and analyze.valid_run_id(run_id) else analyze.new_run_id()
    spec = {"run_id": run_id, "link": link, "repo": parsed["repo"], "status": "running",
            "created_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"), "site_url": site_url,
            "overrides": overrides}
    _save_spec(run_id, spec)
    emit(run_id, "S0", "site", f"Target received: {link}")
    emit(run_id, "S0", "site", "Orchestrating: S1-S2 engine -> S3 Tracer -> S4 Transformer -> S5 verify "
                               "-> S6 Verifier (AI agents) -> S7 human gate -> S8 draft PR -> S9 artifact")
    if background is None:
        background = not ON_VERCEL  # serverless functions stop when the response is sent
    if background:
        threading.Thread(target=_s0_to_s2, args=(run_id, spec), daemon=True).start()
    else:
        _s0_to_s2(run_id, spec)
    return run_id


def _s0_to_s2(run_id: str, spec: dict) -> None:
    run_dir = _run_dir(run_id)
    try:
        gh = analyze.client()
        emit(run_id, "S0", "site", f"Resolving {spec['repo']} on GitHub (branches, contract folders, history)")
        found, commits, chosen = analyze.resolve(gh, spec["link"], **spec["overrides"])
        for note in found["notes"]:
            emit(run_id, "S0", "site", note)
        base_note = next((c["message"] for c in commits if c["sha"].startswith(chosen["base"])), None)
        emit(run_id, "S0", "site",
             f"Upstream {chosen['upstream'] or '(repo root)'} (contract owner) -> consumer "
             f"{chosen['consumer'] or '(repo root)'}; base {chosen['base'][:12]}"
             + (f" ({base_note})" if base_note else "") + f" -> head {chosen['head']}", "ok")

        result = analyze.run_pipeline(gh, chosen["repo"], chosen["upstream"], chosen["consumer"], chosen["base"],
                                      chosen["head"], on_event=lambda step, msg, level="info": emit(
                                          run_id, step, "tracer" if step == "S2" else "engine", msg, level))
        s = result["summary"]
        emit(run_id, "S2", "tracer", f"S2 trace: {len(result['hits'])} usages in {s['files']} files -> "
                                     f"{', '.join(s['endpoints']) or 'no endpoints'}", "ok")

        upstream_info = {"repo": chosen["repo"], "base": chosen["base"], "head": chosen["head"],
                         "base_sha": result["base_sha"], "head_sha": result["head_sha"]}
        breaking = [c for c in result["changes"] if c["breaking"]]
        (run_dir / "drift.json").write_text(json.dumps({
            "run_id": run_id, "upstream": upstream_info, "changes": result["changes"],
            "summary": {"total": s["total"], "breaking": len(breaking),
                        "by_surface": {x: sum(1 for c in result["changes"] if c["surface"] == x)
                                       for x in ("rest", "grpc", "db")}},
        }, indent=2), encoding="utf-8")
        (run_dir / "candidates.json").write_text(json.dumps({
            "run_id": run_id, "consumer": chosen["consumer"], "hits": result["hits"],
            "summary": {"hits": len(result["hits"]), "files": s["files"], "endpoints": s["endpoints"]},
        }, indent=2), encoding="utf-8")

        params = {"repo": chosen["repo"], "upstream": chosen["upstream"], "consumer": chosen["consumer"],
                  "base": result["base_sha"][:12], "head": chosen["head"], "run": run_id}
        bob_link = f"{spec['site_url'].rstrip('/')}/analyze?{urlencode(params)}"
        spec.update({"status": "traced", "traced_at": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
                     **chosen, "base_sha": result["base_sha"], "head_sha": result["head_sha"],
                     "default_branch": found.get("default_branch"),
                     "summary": s, "hits": len(result["hits"]), "bob_command": f"/syncsnitch {bob_link}",
                     "analyze_url": f"/analyze?{urlencode({k: v for k, v in params.items() if k != 'run'})}"})
        _save_spec(run_id, spec)
        if breaking:
            from . import agents  # noqa: PLC0415 - agents imports this module

            agents.start(run_id)  # logs which engine runs the agents, or what is missing
        else:
            emit(run_id, "S2", "site", "No breaking contract changes: nothing for the agents to do", "ok")
    except analyze.AnalyzeError as e:
        spec.update({"status": "failed", "error": str(e)})
        _save_spec(run_id, spec)
        emit(run_id, "S0", "site", f"Stopped: {e}", "error")
    except Exception as e:  # noqa: BLE001 - surface anything to the page instead of hanging it
        spec.update({"status": "failed", "error": f"{type(e).__name__}: {e}"})
        _save_spec(run_id, spec)
        emit(run_id, "S0", "site", f"Stopped: {type(e).__name__}: {e}", "error")


def ensure(run_id: str, query: dict, site_url: str) -> bool:
    """Serverless instances do not share /tmp: rebuild S0-S2 from the run's URL parameters when missing."""
    if (_run_dir(run_id) / "spec.json").exists():
        return True
    if not query.get("link"):
        return False
    overrides = {k: query[k] for k in ("upstream", "consumer", "base", "head") if query.get(k) is not None}
    launch(query["link"], site_url, overrides, run_id=run_id, background=False)
    return True


# ---------------------------------------------------------------------------
# State: what the live page shows
# ---------------------------------------------------------------------------

def _git(args: list[str]) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _transformer_facts(run_id: str, spec: dict) -> dict:
    """Branch, commits and diffstat of the Transformer's work, straight from git in Bob's clone."""
    work = WORK_DIR / run_id
    if not (work / ".git").exists():
        return {}
    w, consumer, branch = str(work), spec.get("consumer") or ".", f"syncsnitch/{run_id}"
    facts: dict = {"clone": True, "branch": branch}
    if _git(["-C", w, "rev-parse", "--verify", "--quiet", branch]) is None:
        return facts
    head = spec.get("head", "HEAD")
    base = next((r for r in (head, f"origin/{head}") if _git(["-C", w, "rev-parse", "--verify", "--quiet", r])), None)
    facts["branch_exists"] = True
    if base:
        log = _git(["-C", w, "log", "--format=%h%x09%ct%x09%s", f"{base}..{branch}"]) or ""
        facts["commits"] = [dict(zip(("sha", "ts", "subject"), line.split("\t", 2))) for line in log.splitlines() if line]
        names = _git(["-C", w, "diff", "--name-only", f"{base}...{branch}", "--", consumer]) or ""
        facts["files"] = [n for n in names.splitlines() if n]
        stat = _git(["-C", w, "diff", "--shortstat", f"{base}...{branch}", "--", consumer]) or ""
        ins = re.search(r"(\d+) insertion", stat)
        dele = re.search(r"(\d+) deletion", stat)
        facts["insertions"], facts["deletions"] = int(ins.group(1)) if ins else 0, int(dele.group(1)) if dele else 0
    pending = _git(["-C", w, "status", "--porcelain", "--", consumer]) or ""
    facts["uncommitted"] = len([ln for ln in pending.splitlines() if ln.strip()])
    return facts


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds")


def _actions(run_id: str) -> dict | None:
    """GitHub Actions container run for this run id (cached 20 s to stay inside API limits)."""
    now = time.monotonic()
    cached = _ACTIONS_CACHE.get(run_id)
    if cached and now - cached[0] < 20:
        return cached[1]
    result = None
    try:
        gh = analyze.client()
        if gh.has_token:
            wf = gh.find_run(run_id)
            if wf:
                result = {"status": wf["status"], "conclusion": wf.get("conclusion"), "html_url": wf["html_url"]}
                if wf["status"] == "completed":
                    result["verification"] = gh.run_verification(wf)
    except Exception:  # noqa: BLE001 - Actions status is optional
        result = None
    _ACTIONS_CACHE[run_id] = (now, result)
    return result


_HOOK_TEXT = {"PostToolUse": "tool call: {tool}", "PreToolUse": "about to run: {tool}", "Stop": "turn finished"}


def _bob_hook_events(spec: dict) -> list[dict]:
    """IBM Bob's lifecycle-hook log (scripts/bob_hooks/logger.py -> bob_sessions/raw/*.jsonl) since this run's S2.
    Local only; it records tool names and events, never file contents."""
    traced_at = spec.get("traced_at")
    raw = REPO_ROOT / "bob_sessions" / "raw"
    if ON_VERCEL or not traced_at or not raw.is_dir():
        return []
    out: list[dict] = []
    for path in sorted(raw.glob("*.jsonl"))[-2:]:
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            ts = str(rec.get("ts") or "").replace("+00:00", ".000+00:00")
            if ts <= traced_at or rec.get("event") not in _HOOK_TEXT:
                continue
            out.append({"key": f"hook-{path.name}-{i}", "ts": ts, "step": "", "agent": "bob", "level": "info",
                        "msg": _HOOK_TEXT[rec["event"]].format(tool=rec.get("tool") or "?")})
    return out[-80:]


def state(run_id: str) -> dict | None:
    run_dir = _run_dir(run_id)
    spec = _load(run_dir / "spec.json")
    if spec is None:
        return None
    events = [dict(e, key=f"e{i}") for i, e in enumerate(_engine_events().read(RUNS_DIR, run_id))]
    derived: list[dict] = []

    def derive(key: str, path: Path, step: str, agent: str, msg: str, level: str = "info") -> None:
        derived.append({"key": key, "ts": _iso(path.stat().st_mtime), "step": step, "agent": agent,
                        "level": level, "msg": msg})

    artifact = _load(WEB_RUNS / f"{run_id}.json")
    if artifact is None and spec.get("status") == "traced" and ON_VERCEL:
        try:
            artifact = analyze.bob_artifact(analyze.client(), run_id, WEB_RUNS)
        except analyze.AnalyzeError:
            artifact = None
    impact = _load(run_dir / "impact.json") or (artifact or {}).get("impact")
    if impact and (run_dir / "impact.json").exists():
        eps = impact.get("endpoints") or []
        derive("impact", run_dir / "impact.json", "S3", "tracer",
               "impact.json: " + (" · ".join(f"{e.get('endpoint')} {str(e.get('failure', '')).upper()}" for e in eps)
                                  or "written"), "ok")
    tf = _transformer_facts(run_id, spec)
    for c in tf.get("commits", []):
        derived.append({"key": f"commit-{c['sha']}", "ts": _iso(int(c["ts"])), "step": "S4", "agent": "transformer",
                        "level": "ok", "msg": f"commit {c['sha']} on {tf['branch']}: {c['subject']}"})
    verification = _load(run_dir / "verification.json") or (artifact or {}).get("verification")
    if verification and (run_dir / "verification.json").exists():
        for chk in verification.get("checks", []):
            derive(f"check-{chk['id']}-{chk['status']}", run_dir / "verification.json", "S5", "verifier",
                   f"{chk['id']} {chk['name']}: {chk['status'].upper()} - {str(chk.get('details', ''))[:140]}",
                   {"pass": "ok", "fail": "warn"}.get(chk["status"], "info"))
    verdict = _load(run_dir / "verdict.json") or (artifact or {}).get("verdict")
    if verdict and (run_dir / "verdict.json").exists():
        derive("verdict", run_dir / "verdict.json", "S6", "verifier",
               f"verdict.json: {str(verdict.get('verdict', '')).upper()}"
               + (f" - {verdict['reasons'][0]}" if verdict.get("reasons") else ""),
               "ok" if verdict.get("verdict") == "green" else "warn")
    if artifact:
        derived.append({"key": "artifact", "ts": artifact.get("created_at") or _iso(time.time()), "step": "S9",
                        "agent": "engine", "level": "ok",
                        "msg": "S9 run artifact published" + (f" · companion PR {artifact['companion_pr_url']}"
                                                              if artifact.get("companion_pr_url") else "")})
    from . import agents  # noqa: PLC0415 - agents imports this module

    runner = spec.get("runner") or {}
    rstate = runner.get("state")
    if rstate in agents.ACTIVE_STATES and not agents.is_running(run_id):
        # the server restarted while the run was going: resume the agents, or press Approve again to publish
        rstate = "publish_failed" if rstate == "publishing" else "interrupted"
    ragents, rstages = runner.get("agents") or {}, runner.get("stages") or {}
    # Bob IDE's hook log only matters when the agents were started by hand in the IDE, not by this runner
    hook_events = _bob_hook_events(spec) if rstate in (None, "blocked") else []
    all_events = sorted(events + derived + hook_events, key=lambda e: e["ts"])

    def seen(step: str, agent: str | None = None, level: str | None = None) -> bool:
        return any(e["step"] == step and (agent is None or e["agent"] == agent) and (level is None or e["level"] == level)
                   for e in events)

    # anything recorded after the website finished S1-S2 comes from IBM Bob's run (its CLI steps or agents)
    traced_at = spec.get("traced_at") or "9999"
    bob_active = any(e["ts"] > traced_at and e["agent"] != "site" for e in events) or bool(hook_events) \
        or bool(impact or tf or verification or verdict or artifact)
    companion = (artifact or {}).get("companion_pr_url") or next(
        (m.group(0) for e in events if e["step"] == "S8" for m in [re.search(r"https://\S+", e["msg"])] if m), None)

    # --- Subagent 1: Schema Diff & AST Tracer (S1-S2 engine here, S3 classification in Bob)
    status = spec.get("status")
    no_drift = status == "traced" and (spec.get("summary") or {}).get("breaking") == 0
    stopped = rstate in ("interrupted", "failed")
    if status == "failed":
        tracer = "failed"
    elif no_drift:
        tracer = "done"
    elif status != "traced":
        tracer = "running"
    elif ragents.get("tracer"):
        tracer = "stopped" if stopped and ragents["tracer"] == "running" else ragents["tracer"]
    elif rstate == "preparing":
        tracer = "running"
    elif impact:
        tracer = "done"
    elif seen("S3", "tracer") or bob_active:
        tracer = "running"
    else:
        tracer = "waiting_bob"
    impact_eps = [e for e in (impact or {}).get("endpoints", []) if isinstance(e, dict)]
    failures = {e.get("endpoint"): str(e.get("failure") or e.get("severity") or "").lower() for e in impact_eps}
    loud = sum(1 for v in failures.values() if v == "loud")
    silent = sum(1 for v in failures.values() if v == "silent")
    silent_why = next((str(e.get("why") or e.get("details") or "")[:140] for e in impact_eps
                       if failures.get(e.get("endpoint")) == "silent"), "")

    # --- Subagent 2: Downstream Code Transformer (S4 in Bob)
    if ragents.get("transformer"):
        transformer = "stopped" if stopped and ragents["transformer"] == "running" else ragents["transformer"]
    elif runner and rstate != "blocked":
        transformer = "waiting"
    elif seen("S4", "transformer", "ok") or tf.get("commits") or (artifact or {}).get("diff"):
        transformer = "done"
    elif seen("S4", "transformer") or tf.get("branch_exists") or tf.get("uncommitted"):
        transformer = "running"
    else:
        transformer = "waiting"

    # --- Subagent 3: Contract Verifier (S5 deterministic + S6 judgement in Bob)
    checks = {c["id"]: c for c in (verification or {}).get("checks", [])}
    legacy = not runner or rstate == "blocked"  # agents started by hand in the Bob IDE, containers in Actions
    actions = _actions(run_id) if status == "traced" and not verification and legacy else None
    if not checks and actions and actions.get("verification"):
        checks = {c["id"]: c for c in actions["verification"].get("checks", [])}
    if ragents.get("verifier"):
        verifier = "stopped" if stopped and ragents["verifier"] == "running" else ragents["verifier"]
        if verifier == "waiting" or (verifier == "running" and rstages.get("verify") == "running"):
            checks = {}  # a fix round or a fresh S5 run: the previous round's checks are not current
    elif runner and rstate != "blocked":
        verifier = "waiting"
    elif verdict:
        verifier = "done"
    elif checks or seen("S5", "verifier") or seen("S6", "verifier") or (actions and actions["status"] != "completed"):
        verifier = "running"
    else:
        verifier = "waiting"
    if ragents.get("verifier") in ("running", "waiting"):
        verdict = None  # the verdict of an earlier round is not the answer to this one

    companion = runner.get("companion_pr_url") or companion
    if status == "failed":
        phase = "failed"
    elif no_drift:
        phase = "no_drift"
    elif rstate == "complete" or artifact or companion:
        phase = "complete"
    elif rstate == "publishing":
        phase = "publishing"
    elif rstate in ("approval", "publish_failed"):
        phase = "approval"
    elif rstate == "rejected":
        phase = "aborted"
    elif rstate in ("failed", "interrupted"):
        phase = rstate
    elif rstate in agents.ACTIVE_STATES:
        phase = "active"
    elif rstate == "blocked" and not bob_active:
        phase = "blocked"
    elif seen("S7", "human") and not seen("S7", "human", "ok") and not seen("S7", "human", "warn"):
        phase = "approval"
    elif seen("S7", "human", "warn"):
        phase = "aborted"
    elif bob_active:
        phase = "active"
    elif status == "traced":
        phase = "waiting_bob"
    else:
        phase = "tracing"

    s = spec.get("summary") or {}
    surfaces = [n for k, n in (("rest", "REST"), ("grpc", "gRPC"), ("db", "DB")) if (s.get("by_surface") or {}).get(k)]
    return {
        "run_id": run_id,
        "phase": phase,
        "spec": {k: spec.get(k) for k in ("link", "repo", "upstream", "consumer", "base", "base_sha", "head",
                                          "created_at", "error", "bob_command", "analyze_url")},
        "tracer": {"status": tracer, "breaking": s.get("breaking"), "surfaces": surfaces, "hits": spec.get("hits"),
                   "by_surface": s.get("by_surface") or {}, "files": s.get("files"),
                   "endpoints": s.get("endpoints") or [], "classified": bool(impact), "loud": loud, "silent": silent,
                   "failures": {k: v for k, v in failures.items() if k and v}, "silent_why": silent_why},
        "transformer": {"status": transformer, "branch": tf.get("branch") or f"syncsnitch/{run_id}",
                        "files": len(tf.get("files", [])) if "files" in tf else None,
                        "insertions": tf.get("insertions"), "deletions": tf.get("deletions"),
                        "uncommitted": tf.get("uncommitted"), "commits": len(tf.get("commits", [])),
                        "unit_tests": (checks.get("V1") or {}).get("status")},
        "verifier": {"status": verifier,
                     "checks": [{"id": f"V{i}", "status": (checks.get(f"V{i}") or {}).get("status", "waiting"),
                                 "details": str((checks.get(f"V{i}") or {}).get("details", ""))[:90]}
                                for i in range(1, 7)],
                     "verdict": (verdict or {}).get("verdict"),
                     "source": "local" if verification else ("actions" if checks else None)},
        "actions": {k: v for k, v in (actions or {}).items() if k != "verification"} or None,
        "companion_pr_url": companion,
        "replay_url": f"/runs/{run_id}" if artifact else None,
        "diff_available": bool(tf.get("commits") or (artifact or {}).get("diff")),
        "diff_key": f"{len(tf.get('commits', []))}:{tf.get('insertions')}:{tf.get('deletions')}:{bool(artifact)}",
        "runner": _runner_view(run_id, runner, rstate),
        "events": all_events,
    }


def _runner_view(run_id: str, runner: dict, rstate: str | None) -> dict | None:
    """What the page needs from the local agent runner: state, Bobcoins, setup problems and allowed actions."""
    from . import agents  # noqa: PLC0415

    if not runner:
        return None
    spent = {k: round(float(v or 0), 2) for k, v in (runner.get("spent") or {}).items()}
    view = {"state": rstate, "backend": runner.get("backend"), "label": runner.get("label"),
            "model": runner.get("model"), "unit": runner.get("unit") or "Bobcoins",
            "budget": runner.get("budget"), "spent": round(sum(spent.values()), 2),
            "spent_by": spent, "tasks": {k: v for k, v in (runner.get("tasks") or {}).items() if v},
            "docker": runner.get("docker"), "error": runner.get("error"), "verdict": runner.get("verdict"),
            "problems": runner.get("problems") or [],
            "can_approve": rstate in ("approval", "publish_failed") and runner.get("verdict") == "green",
            "can_reject": rstate in ("approval", "publish_failed"), "can_start": False}
    if rstate in ("blocked", "failed", "interrupted"):
        status = agents.runner_status()
        view["can_start"] = status["ready"]
        if rstate == "blocked":
            view.update(problems=status["problems"], backend=status["backend"], label=status["label"],
                        model=status["model"], unit=status["unit"], budget=status["budget"])
    return view


def diff_text(run_id: str) -> str:
    """The Transformer's patch: git in Bob's clone, else the diff recorded in the S9 run artifact."""
    spec = _load(_run_dir(run_id) / "spec.json") or {}
    work = WORK_DIR / run_id
    if (work / ".git").exists():
        branch, head = f"syncsnitch/{run_id}", spec.get("head", "HEAD")
        base = next((r for r in (head, f"origin/{head}")
                     if _git(["-C", str(work), "rev-parse", "--verify", "--quiet", r])), None)
        if base and _git(["-C", str(work), "rev-parse", "--verify", "--quiet", branch]):
            text = _git(["-C", str(work), "diff", f"{base}...{branch}", "--", spec.get("consumer") or ".",
                         ":(exclude)*_pb2.py", ":(exclude)*_pb2.pyi", ":(exclude)*_pb2_grpc.py"]) or ""
            if text:
                return "# generated protobuf stubs (*_pb2*.py) are hidden\n" + text[:200_000]
    return str((_load(WEB_RUNS / f"{run_id}.json") or {}).get("diff") or "")[:200_000]


def live_url(run_id: str, spec_link: str, overrides: dict) -> str:
    """The run page URL; the query lets any serverless instance rebuild S0-S2."""
    query = {"link": spec_link, **{k: v for k, v in overrides.items() if v is not None}}
    return f"/live/{run_id}?{urlencode(query)}"
