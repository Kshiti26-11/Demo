"""The local SyncSnitch runner: after the website's S1-S2 it drives the whole run, with no step in the Bob IDE.

  S2  prepare      clone the repo into .syncsnitch/work/<run_id>, branch syncsnitch/<run_id>, change proposal (0 tokens)
  S3  Tracer       IBM Bob Shell `bob run --mode syncsnitch-tracer`       -> impact.json
  S4  Transformer  IBM Bob Shell `bob run --mode syncsnitch-transformer`  -> commits on syncsnitch/<run_id>
  S5  verify       `syncsnitch verify` (deterministic; Docker mock containers when Docker is running)
  S6  Verifier     IBM Bob Shell `bob run --mode syncsnitch-verifier`     -> verdict.json (+1 fix round if red)
  S7  gate         the human approves or rejects on the run page
  S8  draft PR     scripts/open_companion_pr.sh (0 tokens), after the approval only
  S9  artifact     web/runs/<run_id>.json (0 tokens)

The three agents are the custom modes in .bob/custom_modes.yaml, run headless by IBM Bob Shell. Their stream-json
output goes into the run's event log, and every status on the page comes from the files and git state they leave
behind. A Bobcoin budget caps each run (SYNCSNITCH_BOB_BUDGET, default 5).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from . import live, llm_agent

REPO_ROOT = live.REPO_ROOT
ENV_FILES = (REPO_ROOT / ".env", REPO_ROOT / ".env.local")  # later files win; real environment variables win over both
_ENV_KEYS = ("BOB_API_KEY", "BOB_TEAM_ID", "SYNCSNITCH_BOB_BUDGET", "SYNCSNITCH_AGENT_BACKEND", "SYNCSNITCH_TOKEN_BUDGET",
             "GEMINI_API_KEY", "SYNCSNITCH_GEMINI_MODEL", "XAI_API_KEY", "SYNCSNITCH_GROK_MODEL",
             "ANTHROPIC_API_KEY", "SYNCSNITCH_CLAUDE_MODEL",
             "SYNCSNITCH_CLAUDE_TOKEN_BUDGET")
ENGINES = ("bob", "gemini", "grok", "claude")  # IBM Bob Shell, or an API model through llm_agent.py
LABELS = {"bob": "IBM Bob", **{k: v["label"] for k, v in llm_agent.PROVIDERS.items()}}
UNITS = {"bob": "Bobcoins", **{k: "tokens" for k in llm_agent.PROVIDERS}}
BOB_SETTINGS = Path.home() / ".bob" / "settings" / "settings.json"
ACTIVE = REPO_ROOT / ".syncsnitch" / "ACTIVE"  # read by the write-guard hook (scripts/bob_hooks/guard.py)
MODES = {"tracer": "syncsnitch-tracer", "transformer": "syncsnitch-transformer", "verifier": "syncsnitch-verifier"}
STEPS = {"tracer": "S3", "transformer": "S4", "verifier": "S6"}
TIMEOUTS = {"tracer": 900, "transformer": 1800, "verifier": 600}  # seconds per Bob session
MAX_TURNS = {"tracer": 40, "transformer": 80, "verifier": 20}
VERIFY_TIMEOUT = 1800
ACTIVE_STATES = ("preparing", "tracer", "transformer", "verify", "verifier", "publishing")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

_THREADS: dict[str, threading.Thread] = {}
_THREADS_LOCK = threading.Lock()
_SPEC_LOCK = threading.RLock()
_DOCKER = {"checked": 0.0, "ok": False}


class StageError(Exception):
    """A stage could not finish; the message is shown on the run page."""


# ---------------------------------------------------------------------------
# Setup checks
# ---------------------------------------------------------------------------

def local_env() -> dict[str, str]:
    """BOB_API_KEY and friends from .env / .env.local in the repo root (both gitignored), then the environment."""
    values: dict[str, str] = {}
    for path in ENV_FILES:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.removeprefix("export ").partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key in _ENV_KEYS and value:
                values[key] = value
    for key in _ENV_KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def budget(backend: str | None = "bob") -> float:
    """The per-run budget: Bobcoins for IBM Bob, processed tokens for an API model (Grok, Claude)."""
    env = local_env()
    if backend in llm_agent.PROVIDERS:
        raw = env.get("SYNCSNITCH_TOKEN_BUDGET") or env.get("SYNCSNITCH_CLAUDE_TOKEN_BUDGET") or 3_000_000
        try:
            return float(max(50_000, int(float(raw))))
        except ValueError:
            return 3_000_000.0
    try:
        return max(0.5, float(env.get("SYNCSNITCH_BOB_BUDGET") or 5))
    except ValueError:
        return 5.0


def bob_bin() -> str | None:
    override = os.environ.get("SYNCSNITCH_BOB_BIN")
    if override:
        return override if Path(override).exists() else shutil.which(override)
    return shutil.which("bob") or next((p for p in ("/opt/homebrew/bin/bob", "/usr/local/bin/bob") if Path(p).exists()),
                                       None)


def license_accepted() -> bool:
    """Bob Shell stores the IBM license consent in ~/.bob/settings/settings.json (`bob --accept-license`)."""
    if os.environ.get("SYNCSNITCH_BOB_BIN"):  # a stand-in binary (tests) has no license
        return True
    try:
        return json.loads(BOB_SETTINGS.read_text(encoding="utf-8")).get("licenseConsent") is True
    except (OSError, ValueError):
        return False


def _docker_bin() -> str | None:
    return shutil.which("docker") or next(
        (p for p in ("/usr/local/bin/docker", "/opt/homebrew/bin/docker",
                     "/Applications/Docker.app/Contents/Resources/bin/docker") if Path(p).exists()), None)


def docker_ready() -> bool:
    """True when a Docker engine answers (checked at most every 30 s)."""
    if os.environ.get("SYNCSNITCH_NO_CONTAINERS"):
        return False
    now = time.monotonic()
    if _DOCKER["checked"] and now - _DOCKER["checked"] < 30:
        return _DOCKER["ok"]
    docker, ok = _docker_bin(), False
    if docker:
        try:
            ok = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True,
                                timeout=10).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
    _DOCKER.update(checked=now, ok=ok)
    return ok


def _bob_problems(env: dict) -> list[dict]:
    problems = []
    if not bob_bin():
        problems.append({"id": "bob", "text": "IBM Bob Shell (the `bob` command) is not installed.",
                         "fix": "curl -fsSL https://bob.ibm.com/download/bobshell.sh | bash"})
    if not env.get("BOB_API_KEY"):
        problems.append({"id": "key", "text": "No IBM Bob API key: headless Bob sessions need BOB_API_KEY.",
                         "fix": "bash scripts/bob_setup.sh"})
    elif bob_bin() and not license_accepted():
        problems.append({"id": "license", "text": "The IBM Bob Shell license has not been accepted on this machine.",
                         "fix": "bash scripts/bob_setup.sh"})
    return problems


def _api_problems(env: dict, provider: str) -> list[dict]:
    p = llm_agent.PROVIDERS[provider]
    if env.get(p["key"]):
        return []
    return [{"id": provider, "text": f"No {p['label']} API key ({p['key']}) saved for the agents.", "fix": p["setup"]}]


def choose_backend(env: dict | None = None) -> tuple[str | None, list[dict]]:
    """Which engine runs the three agents: SYNCSNITCH_AGENT_BACKEND=bob|gemini|grok|claude, or auto (the first of
    IBM Bob, Gemini, Grok, Claude that is set up). Returns the engine and what is missing for it."""
    env = local_env() if env is None else env
    pref = (env.get("SYNCSNITCH_AGENT_BACKEND") or "auto").strip().lower()
    missing = {"bob": _bob_problems(env), **{k: _api_problems(env, k) for k in llm_agent.PROVIDERS}}
    if pref in missing:
        return pref, missing[pref]
    ready = next((e for e in ENGINES if not missing[e]), None)
    if ready:
        return ready, []
    return None, [
        {"id": "gemini", "text": "No agent engine is set up. Run the agents on Gemini (a free Google AI Studio key; "
                                 "free-tier data may be used by Google)…", "fix": "bash scripts/gemini_setup.sh"},
        {"id": "grok", "text": "…or on Grok (an xAI API key with credits)…", "fix": "bash scripts/grok_setup.sh"},
        {"id": "claude", "text": "…or on Claude (an Anthropic API key with credits)…",
         "fix": "bash scripts/claude_setup.sh"},
        {"id": "bob", "text": "…or on IBM Bob (IBM Bob Shell and a Bob API key; spends Bobcoins).",
         "fix": "bash scripts/bob_setup.sh"}]


def runner_status() -> dict:
    """Can this server run the three agents by itself? Lists what is missing and the command that fixes it."""
    if live.ON_VERCEL:
        return {"ready": False, "where": "vercel", "backend": None, "label": None, "model": None, "unit": "Bobcoins",
                "docker": False, "budget": budget(), "problems": [{
                    "id": "vercel", "text": "The agents run on the SyncSnitch runner: this site running on a machine "
                                            "with IBM Bob Shell or a Gemini / Grok / Claude key. Serverless functions "
                                            "cannot host an agent session.",
                    "fix": "git clone https://github.com/kshiti26-11/demo && cd demo && uv sync && "
                           "bash scripts/run_site.sh"}]}
    env = local_env()
    backend, problems = choose_backend(env)
    problems = list(problems)
    if not (Path(sys.executable).with_name("syncsnitch").exists() or shutil.which("uv")):
        problems.append({"id": "engine", "text": "The syncsnitch engine is not installed in this environment.",
                         "fix": "uv sync"})
    model = llm_agent.model_of(backend, env) if backend in llm_agent.PROVIDERS else None
    return {"ready": backend is not None and not problems, "where": "local", "backend": backend,
            "label": LABELS.get(backend), "model": model, "unit": UNITS.get(backend, "Bobcoins"),
            "docker": docker_ready(), "budget": budget(backend), "problems": problems}


# ---------------------------------------------------------------------------
# Run state (kept in spec.json under "runner")
# ---------------------------------------------------------------------------

def _spec(run_id: str) -> dict:
    return live._load(live._run_dir(run_id) / "spec.json") or {}


def _update(run_id: str, **changes) -> dict:
    """Merge `changes` into spec["runner"]; nested dicts (agents, spent, tasks) are merged one level deep."""
    with _SPEC_LOCK:
        spec = _spec(run_id)
        runner = spec.setdefault("runner", {})
        for key, value in changes.items():
            if isinstance(value, dict) and isinstance(runner.get(key), dict):
                runner[key].update(value)
            else:
                runner[key] = value
        runner["updated_at"] = datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")
        live._save_spec(run_id, spec)
        return runner


def is_running(run_id: str) -> bool:
    with _THREADS_LOCK:
        t = _THREADS.get(run_id)
        return bool(t and t.is_alive())


def _start_thread(run_id: str, target, *args) -> bool:
    with _THREADS_LOCK:
        t = _THREADS.get(run_id)
        if t and t.is_alive():
            return False
        t = threading.Thread(target=target, args=(run_id, *args), daemon=True, name=f"syncsnitch-{run_id}")
        _THREADS[run_id] = t
        t.start()
        return True


def emit(run_id: str, step: str, agent: str, msg: str, level: str = "info", src: str | None = None) -> None:
    live._engine_events().emit(live.RUNS_DIR, run_id, step, agent, msg, level, src)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def start(run_id: str) -> bool:
    """Start (or resume) S2 prepare -> S7 gate for a traced run. Returns False when it cannot start here."""
    spec = _spec(run_id)
    if spec.get("status") != "traced" or not (spec.get("summary") or {}).get("breaking"):
        return False
    status = runner_status()
    if not status["ready"]:
        first = status["problems"][0]
        _update(run_id, state="blocked", problems=status["problems"], budget=status["budget"])
        if status["where"] == "vercel":
            emit(run_id, "S2", "site", "S1-S2 done. The agents run on the local SyncSnitch runner, not on this "
                                       "serverless deployment", "warn")
        else:
            emit(run_id, "S2", "site", f"Cannot start the agents: {first['text']} Fix: {first['fix']}", "error")
        return False
    runner = spec.get("runner") or {}
    if runner.get("state") in ("approval", "publishing", "complete", "rejected") or is_running(run_id):
        return False
    backend, same = status["backend"], runner.get("backend") == status["backend"]
    if runner.get("backend") and not same:  # budgets are in different units: the new engine starts from zero
        with _SPEC_LOCK:
            spec = _spec(run_id)
            spec["runner"]["spent_before_switch"] = {runner["backend"]: spec["runner"].pop("spent", {})}
            live._save_spec(run_id, spec)
        emit(run_id, "S2", "site", f"Resuming on {LABELS[backend]} (this run started on "
                                   f"{LABELS.get(runner['backend'], runner['backend'])})", "warn")
    fresh = not runner.get("started_at")
    _update(run_id, state="preparing", problems=[], error=None, backend=backend, label=LABELS[backend],
            model=status["model"], unit=UNITS[backend],
            budget=runner.get("budget") if same and runner.get("budget") else status["budget"],
            docker=status["docker"],
            started_at=runner.get("started_at") or datetime.now(tz=timezone.utc).isoformat(timespec="seconds"))
    if fresh:
        emit(run_id, "S2", "site", f"S1-S2 done: starting the 3 agents on {LABELS[backend]}"
                                   + (f" ({status['model']})" if status["model"] else "")
                                   + " - Tracer -> Transformer -> Verifier, no IDE step needed", "ok")
    return _start_thread(run_id, _pipeline)


def _gate_open(run_id: str) -> bool:
    state = (_spec(run_id).get("runner") or {}).get("state")
    return state in ("approval", "publish_failed") or (state == "publishing" and not is_running(run_id))


def approve(run_id: str) -> None:
    runner = _spec(run_id).get("runner") or {}
    if not _gate_open(run_id):
        raise StageError("this run is not waiting for approval")
    if runner.get("verdict") != "green":
        raise StageError("the Verifier's verdict is not green: nothing can be published")
    _update(run_id, state="publishing", error=None)
    emit(run_id, "S7", "human", "Approved by the human on the run page", "ok")
    _start_thread(run_id, _publish)


def reject(run_id: str) -> None:
    if not _gate_open(run_id):
        raise StageError("this run is not waiting for approval")
    _update(run_id, state="rejected")
    emit(run_id, "S7", "human", "Rejected by the human: nothing was pushed and no PR was opened", "warn")


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

def _ctx(run_id: str) -> dict:
    spec = _spec(run_id)
    work = live.WORK_DIR / run_id
    up, cons = spec.get("upstream") or "", spec.get("consumer") or ""

    def rel(p: Path) -> str:
        try:
            return str(p.relative_to(REPO_ROOT))
        except ValueError:
            return str(p)

    head_sha = spec.get("head_sha") or spec.get("head")
    return {
        "run_id": run_id, "spec": spec, "repo": spec["repo"], "work": work, "work_rel": rel(work),
        "up": up, "cons": cons, "up_path": work / up if up else work, "cons_path": work / cons if cons else work,
        "up_rel": rel(work / up if up else work), "cons_rel": rel(work / cons if cons else work),
        "run_rel": rel(live.RUNS_DIR / run_id), "run_dir": live.RUNS_DIR / run_id,
        "base_sha": spec.get("base_sha") or spec.get("base"), "head": spec.get("head"), "head_sha": head_sha,
        "branch": f"syncsnitch/{run_id}",
        "compare_url": f"https://github.com/{spec['repo']}/compare/{(spec.get('base_sha') or spec.get('base'))[:12]}"
                       f"...{spec.get('head')}",
    }


def _pipeline(run_id: str) -> None:
    """S2 prepare -> S3 -> S4 -> (S5 -> S6, plus one fix round S4 -> S5 -> S6 when red) -> S7 gate.
    A resumed run skips the agents that already finished and continues an interrupted fix round."""
    ctx = _ctx(run_id)
    runner = _spec(run_id).get("runner") or {}
    stages, rounds = runner.get("stages") or {}, int(runner.get("round") or 0)
    try:
        _prepare(ctx)
        if stages.get("tracer") != "done":
            _tracer(ctx)
        if stages.get("transformer") != "done":
            _transformer(ctx, fix=(live._load(ctx["run_dir"] / "verdict.json") or {}) if rounds else None)
        while True:
            _verify(ctx)
            verdict = _verifier(ctx)
            if verdict["verdict"] == "green" or rounds >= 1:
                break
            if not verdict.get("fix_instructions"):
                emit(run_id, "S6", "verifier", "RED without fix instructions: no automatic fix round", "warn")
                break
            left = _left(run_id)
            if left < 1.5:
                emit(run_id, "S6", "verifier", f"RED: {left:.2f} Bobcoins left in this run's budget, not enough for an "
                                               "automatic fix round", "warn")
                break
            rounds += 1
            _update(run_id, round=rounds)
            emit(run_id, "S6", "verifier", "RED: routing the fix instructions back to the Transformer (fix round 1)",
                 "warn")
            _transformer(ctx, fix=verdict)
        _gate(ctx, verdict)
    except StageError as e:
        _fail(run_id, str(e))
    except Exception as e:  # noqa: BLE001 - never leave the page spinning
        _fail(run_id, f"{type(e).__name__}: {e}")
    finally:
        _release_guard(ctx)


def _fail(run_id: str, message: str) -> None:
    runner = _spec(run_id).get("runner") or {}
    step = {"tracer": "S3", "transformer": "S4", "verify": "S5", "verifier": "S6"}.get(runner.get("state"), "S2")
    agents = {k: "failed" for k, v in (runner.get("agents") or {}).items() if v == "running"}
    _update(run_id, state="failed", error=message, agents=agents)
    emit(run_id, step, "site", f"Run stopped: {message}. Fix it and press Resume agents", "error")


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 300, env: dict | None = None) -> tuple[int, str]:
    try:
        out = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout,
                             env=env, stdin=subprocess.DEVNULL)
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout} s: {' '.join(cmd[:4])}"
    except OSError as e:
        return 127, str(e)


def _git(ctx: dict, *args: str, timeout: int = 120) -> tuple[int, str]:
    return _run(["git", "-C", str(ctx["work"]), *args], timeout=timeout)


def _tail(text: str, n: int = 3) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return " | ".join(lines[-n:])[:400]


def _engine() -> list[str]:
    exe = Path(sys.executable).with_name("syncsnitch")
    if exe.exists():
        return [str(exe)]
    return [shutil.which("uv") or "uv", "run", "--project", str(REPO_ROOT), "syncsnitch"]


# --- S2 prepare (deterministic) ---------------------------------------------

def _clone_cmd(repo: str, dest: Path) -> list[str]:
    """gh uses your GitHub login (private repos work too); plain git for public repos otherwise."""
    gh = shutil.which("gh")
    if gh:
        return [gh, "repo", "clone", repo, str(dest), "--", "--quiet"]
    return ["git", "clone", "--quiet", f"https://github.com/{repo}.git", str(dest)]


def _prepare(ctx: dict) -> None:
    run_id, work = ctx["run_id"], ctx["work"]
    _update(run_id, state="preparing")
    if not (work / ".git").exists():
        emit(run_id, "S2", "engine", f"Preparing the agents' workspace: cloning {ctx['repo']} into {ctx['work_rel']}")
        if work.exists():
            shutil.rmtree(work)  # a half-finished clone from an interrupted run
        work.parent.mkdir(parents=True, exist_ok=True)
        code, out = _run(_clone_cmd(ctx["repo"], work), timeout=600)
        if code != 0:
            raise StageError(f"could not clone {ctx['repo']}: {_tail(out)}")
    else:
        _git(ctx, "fetch", "--quiet", "origin", timeout=180)
    if _git(ctx, "rev-parse", "--verify", "--quiet", ctx["branch"])[0] == 0:
        code, out = _git(ctx, "checkout", "--quiet", ctx["branch"])
    else:
        code, out = _git(ctx, "checkout", "--quiet", "-b", ctx["branch"], ctx["head_sha"])
    if code != 0:
        raise StageError(f"could not check out {ctx['branch']}: {_tail(out)}")
    for ref in (ctx["base_sha"], ctx["head_sha"]):
        if _git(ctx, "cat-file", "-e", f"{ref}^{{commit}}")[0] != 0:
            raise StageError(f"commit {ref[:12]} is not in the clone")
    emit(run_id, "S2", "engine", f"Workspace ready: branch {ctx['branch']} from {ctx['head']} "
                                 f"({ctx['head_sha'][:12]}); upstream {ctx['up'] or '(root)'} is read-only", "ok")
    _copy_proposal(ctx)
    _guard(ctx)


def _copy_proposal(ctx: dict) -> None:
    """The upstream's change proposal (docs/*proposal*.docx|md|pdf) for the Tracer's document understanding."""
    if any(ctx["run_dir"].glob("change-proposal.*")):
        return  # copied earlier
    docs = f"{ctx['up']}/docs" if ctx["up"] else "docs"
    code, out = _git(ctx, "ls-tree", "-r", "--name-only", ctx["head_sha"], "--", docs)
    names = [n for n in out.splitlines() if n.lower().endswith((".docx", ".md", ".pdf", ".txt"))] if code == 0 else []
    if not names:
        return
    names.sort(key=lambda n: (not re.search(r"proposal|change|migration|rfc|adr", n.lower()), n))
    try:
        data = subprocess.run(["git", "-C", str(ctx["work"]), "show", f"{ctx['head_sha']}:{names[0]}"],
                              capture_output=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return
    if data:
        suffix = Path(names[0]).suffix.lower()
        (ctx["run_dir"] / f"change-proposal{suffix}").write_bytes(data)
        emit(ctx["run_id"], "S2", "engine", f"Upstream change proposal found: {names[0]} (the Tracer reads it)")


def _guard(ctx: dict) -> None:
    """Turn on the write guard hook (scripts/bob_hooks/guard.py) for the upstream folder while Bob works."""
    if ctx["up"]:
        ACTIVE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE.write_text(ctx["up_rel"] + "\n", encoding="utf-8")


def _release_guard(ctx: dict) -> None:
    try:
        if ACTIVE.read_text(encoding="utf-8").strip() == ctx["up_rel"]:
            ACTIVE.unlink()
    except OSError:
        pass


# --- the agents (IBM Bob Shell, or an API model: Grok, Claude) ----------------

def _spent(run_id: str) -> float:
    return round(sum(float(v or 0) for v in ((_spec(run_id).get("runner") or {}).get("spent") or {}).values()), 4)


def _backend(run_id: str) -> str:
    return (_spec(run_id).get("runner") or {}).get("backend") or "bob"


def _left(run_id: str) -> float:
    runner = _spec(run_id).get("runner") or {}
    return round(float(runner.get("budget") or budget(_backend(run_id))) - _spent(run_id), 4)


def _cap(run_id: str, agent: str) -> float:
    """This agent's share of what is left: the Tracer up to 30 %, the Transformer all but 15 % (for the Verifier)."""
    backend = _backend(run_id)
    left, total = _left(run_id), float((_spec(run_id).get("runner") or {}).get("budget") or budget(backend))
    if agent == "tracer":
        cap = min(left - total * 0.2, total * 0.3)
    elif agent == "transformer":
        cap = left - total * 0.15
    else:
        cap = left
    if cap < (0.25 if backend == "bob" else 20_000):
        what = ("Bobcoin", "SYNCSNITCH_BOB_BUDGET") if backend == "bob" else ("token", "SYNCSNITCH_TOKEN_BUDGET")
        fmt = ",.2f" if backend == "bob" else ",.0f"
        raise StageError(f"the {what[0]} budget for this run is used up ({_spent(run_id):{fmt}} of {total:{fmt}} "
                         f"spent). Raise {what[1]} in .env.local to continue")
    return round(cap, 2)


def _trailer(run_id: str) -> str:
    runner = _spec(run_id).get("runner") or {}
    if runner.get("backend") in llm_agent.PROVIDERS:
        return f"SyncSnitch-Agent: {LABELS[runner['backend']]} {runner.get('model')} ({run_id})"
    return f"Bob-Session: {run_id}"


def _clean(line: str) -> str:
    return re.sub(r"^[#>*\-\s]+|[*`]+", "", str(line)).strip()


def _short(ctx: dict, text: str) -> str:
    text = str(text).replace(str(REPO_ROOT) + "/", "")
    return text.replace(ctx["work_rel"] + "/", "").replace(ctx["run_rel"] + "/", "run/")


_PATH_KEYS = ("path", "file_path", "target_file", "file", "dir", "directory")


def _describe_tool(ctx: dict, name: str, params) -> str:
    p = params if isinstance(params, dict) else {}
    if isinstance(params, str):
        try:
            p = json.loads(params)
        except ValueError:
            p = {"value": params}
    if p.get("command"):
        return f"$ {_short(ctx, p['command'])[:220]}"
    paths = [str(p[k]) for k in _PATH_KEYS if isinstance(p.get(k), str)]
    for key in ("files", "paths", "args"):
        items = p.get(key)
        if isinstance(items, list):
            paths += [str(i.get("path") if isinstance(i, dict) else i) for i in items if i][:6]
        elif isinstance(items, dict) and isinstance(items.get("file"), (list, dict)):
            files = items["file"] if isinstance(items["file"], list) else [items["file"]]
            paths += [str(f.get("path")) for f in files if isinstance(f, dict)][:6]
    what = ", ".join(_short(ctx, x) for x in paths)
    for key in ("regex", "pattern", "query"):
        if p.get(key):
            what = (what + " " if what else "") + f"/{str(p[key])[:60]}/"
    if name in ("attempt_completion",) and p.get("result"):
        return "result: " + str(p["result"]).strip().splitlines()[0][:200]
    if name == "update_todo_list" and p.get("todos"):
        items = [ln.strip() for ln in str(p["todos"]).splitlines() if ln.strip()][:5]
        return "plan: " + " · ".join(items)[:220]
    return f"{name}" + (f" · {what}" if what else "")


class _Stream:
    """Turns Bob Shell's stream-json events into readable log lines for the run page."""

    def __init__(self, ctx: dict, agent: str):
        self.ctx, self.agent, self.step = ctx, agent, STEPS[agent]
        self.buf, self.cost, self.task_id, self.errors, self.result = "", 0.0, None, [], None
        self.tools: dict[str, str] = {}

    def say(self, msg: str, level: str = "info") -> None:
        emit(self.ctx["run_id"], self.step, self.agent, msg, level, "bob")

    def text(self, line: str) -> None:
        line = _clean(line)
        if line:
            self.say(_short(self.ctx, line)[:300])

    def flush(self) -> None:
        if self.buf.strip():
            for line in self.buf.splitlines():
                self.text(line)
        self.buf = ""

    def feed(self, ev: dict) -> None:
        kind = ev.get("type")
        if kind == "message":
            if ev.get("role") != "assistant" or ev.get("isReasoning"):
                return
            self.buf += str(ev.get("content") or "")
            while "\n" in self.buf:
                line, self.buf = self.buf.split("\n", 1)
                self.text(line)
        elif kind == "tool_use":
            self.flush()
            name = str(ev.get("tool_name") or "tool")
            self.tools[str(ev.get("tool_id") or "")] = name
            self.say(_describe_tool(self.ctx, name, ev.get("parameters")))
        elif kind == "tool_result":
            if ev.get("status") == "error":
                self.flush()
                err = ev.get("error") or {}
                msg = err.get("message") if isinstance(err, dict) else err
                name = self.tools.get(str(ev.get("tool_id") or ""), "tool")
                self.say(f"{name} failed: {_short(self.ctx, str(msg or ''))[:220]}", "warn")
        elif kind == "result":
            self.flush()
            stats = ev.get("stats") or {}
            self.result = ev
            self.cost = float(stats.get("session_costs") or 0)
            self.task_id = stats.get("task_id")
            secs = int((stats.get("duration_ms") or 0) / 1000)
            self.say(f"IBM Bob session finished: {stats.get('tool_calls', 0)} tool calls · {self.cost:.2f} Bobcoins · "
                     f"{secs // 60}m {secs % 60:02d}s" + (f" · task {self.task_id}" if self.task_id else ""), "ok")
        elif kind == "error":
            self.flush()
            msg = str(ev.get("message") or "error")
            self.errors.append(msg)
            m = re.search(r"spent:\s*([0-9.]+)", msg)
            if m:
                self.cost = max(self.cost, float(m.group(1)))
            self.say(_short(self.ctx, msg)[:300], "error")


def _bob(ctx: dict, agent: str, prompt: str) -> _Stream:
    """Run one IBM Bob Shell session headless and stream it into the event log."""
    run_id = ctx["run_id"]
    cap = _cap(run_id, agent)
    env = {**os.environ, **{k: v for k, v in local_env().items() if k.startswith("BOB_")}}
    cmd = [bob_bin() or "bob", "run", "--workspace", str(REPO_ROOT), "--mode", MODES[agent], "--format", "stream-json",
           "--max-cost", f"{cap:.2f}", "--max-turns", str(MAX_TURNS[agent]), "--trust", "--disable-mcp",
           "--disable-subagents"]
    if env.get("BOB_TEAM_ID"):
        cmd += ["--team-id", env["BOB_TEAM_ID"]]
    cmd += ["--", prompt]
    log_dir = ctx["run_dir"] / "bob"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{agent}.prompt.md").write_text(prompt, encoding="utf-8")
    emit(run_id, STEPS[agent], agent, f"IBM Bob Shell · mode {MODES[agent]} · budget {cap:.2f} Bobcoins", "info", "bob")
    stream, stderr_tail = _Stream(ctx, agent), deque(maxlen=40)
    base = float(((_spec(run_id).get("runner") or {}).get("spent") or {}).get(agent) or 0)  # earlier rounds
    try:
        proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1, start_new_session=True)
    except OSError as e:
        raise StageError(f"could not start IBM Bob Shell: {e}") from e
    _update(run_id, pids={agent: proc.pid})

    def read_stderr() -> None:
        with (log_dir / f"{agent}.stderr.log").open("a", encoding="utf-8") as fh:
            for line in proc.stderr:
                fh.write(line)
                if line.strip():
                    stderr_tail.append(line.strip())

    def kill() -> None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass

    threading.Thread(target=read_stderr, daemon=True).start()
    watchdog = threading.Timer(TIMEOUTS[agent], kill)
    watchdog.start()
    try:
        with (log_dir / f"{agent}.ndjson").open("a", encoding="utf-8") as raw:
            for line in proc.stdout:
                raw.write(line)
                raw.flush()
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    stream.text(line)
                    continue
                if isinstance(ev, dict):
                    stream.feed(ev)
                    if ev.get("type") in ("result", "error"):
                        _update(run_id, spent={agent: round(base + stream.cost, 4)})
        code = proc.wait()
    finally:
        watchdog.cancel()
    stream.flush()
    _update(run_id, spent={agent: round(base + stream.cost, 4)}, tasks={agent: stream.task_id}, pids={agent: None})
    if code != 0 and stream.result is None:
        reason = stream.errors[-1] if stream.errors else (stderr_tail[-1] if stderr_tail else f"exit code {code}")
        if code in (-signal.SIGTERM, 143) and not stream.errors:
            reason = f"no result after {TIMEOUTS[agent] // 60} minutes (stopped)"
        stream.errors.append(_short(ctx, reason))
        emit(run_id, STEPS[agent], agent, f"IBM Bob session ended without a result: {_short(ctx, reason)[:300]}",
             "error", "bob")
    return stream


def _api_agent(ctx: dict, agent: str, prompt: str, provider: str) -> llm_agent.Result:
    """Run one agent on an API model (Gemini, Grok or Claude) and stream it into the event log."""
    run_id = ctx["run_id"]
    cap = int(_cap(run_id, agent))
    env = local_env()
    model, label = llm_agent.model_of(provider, env), LABELS[provider]
    log_dir = ctx["run_dir"] / provider
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{agent}.prompt.md").write_text(prompt, encoding="utf-8")
    base = float(((_spec(run_id).get("runner") or {}).get("spent") or {}).get(agent) or 0)  # earlier rounds
    emit(run_id, STEPS[agent], agent, f"{label} ({model}) · agent {MODES[agent]} · budget {cap:,} tokens", "info",
         provider)

    def say(msg: str, level: str = "info") -> None:
        line = _clean(msg)
        if line:
            emit(run_id, STEPS[agent], agent, _short(ctx, line)[:300], level, provider)

    used = {"tokens": 0}

    def on_usage(tokens: int) -> None:
        used["tokens"] = tokens
        _update(run_id, spent={agent: base + tokens})

    try:
        res = llm_agent.run(provider, ctx, agent, prompt, cap, env, say,
                            lambda name, args: _describe_tool(ctx, name, args), on_usage)
    except Exception as e:  # noqa: BLE001 - a broken session must not kill the run silently
        res = llm_agent.Result(cost=used["tokens"], errors=[f"{type(e).__name__}: {e}"])  # keep what was spent
        say(f"{label} session crashed: {type(e).__name__}: {e}", "error")
    _update(run_id, spent={agent: base + res.cost}, tasks={agent: res.task_id})
    return res


def _agent(ctx: dict, agent: str, prompt: str):
    """One agent session on the run's engine (IBM Bob Shell or an API model); returns .errors, .cost, .task_id."""
    backend = _backend(ctx["run_id"])
    return _api_agent(ctx, agent, prompt, backend) if backend in llm_agent.PROVIDERS else _bob(ctx, agent, prompt)


def _set_agent(run_id: str, agent: str, status: str, state: str | None = None) -> None:
    _update(run_id, agents={agent: status}, stages={agent: status}, **({"state": state} if state else {}))


# --- S3 Tracer ---------------------------------------------------------------

def _tracer(ctx: dict) -> None:
    run_id, run_rel = ctx["run_id"], ctx["run_rel"]
    _set_agent(run_id, "tracer", "running", "tracer")
    emit(run_id, "S3", "tracer", "Tracer started: classifying every traced usage as loud or silent")
    proposal = next(iter(sorted(ctx["run_dir"].glob("change-proposal.*"))), None)
    prompt = f"""SyncSnitch run {run_id}, step S3. You are Subagent 1, the Schema Diff & AST Tracer, running headless from the SyncSnitch website: never ask questions, never edit source code, keep replies short.
Paths are relative to the workspace root. Upstream (the contract owner, read-only): {ctx['up_rel']}. Consumer: {ctx['cons_rel']}.
1. Read {run_rel}/drift.json (the contract changes) and {run_rel}/candidates.json (every consumer usage the deterministic scanner found; its file paths are relative to {ctx['cons_rel']}).{f" Read the upstream change proposal {run_rel}/{proposal.name} too." if proposal else ""}
2. Read only the consumer files candidates.json lists. Confirm or reject each usage and add any the scanner missed.
3. Write {run_rel}/impact.json with exactly this shape:
{{"run_id": "{run_id}", "mapping": [{{"change_ids": ["..."], "old": "...", "new": "...", "rule": "..."}}], "affected": [{{"file": "...", "line": 1, "symbol": "...", "change_ids": ["..."], "surface": "rest|grpc|db|test", "failure": "loud|silent|none", "endpoint": "METHOD /path or null", "fix": "..."}}], "endpoints": [{{"endpoint": "METHOD /path", "surface": "rest|grpc|db", "failure": "loud|silent", "why": "..."}}], "migration_notes": "3-6 sentences{' quoting the proposal' if proposal else ''}"}}
"loud" = the endpoint fails with an error; "silent" = it returns wrong data without any error. List every consumer endpoint that breaks.
4. Reply with a 5-line summary."""
    stream = _agent(ctx, "tracer", prompt)
    impact = live._load(ctx["run_dir"] / "impact.json")
    if not isinstance(impact, dict) or not isinstance(impact.get("endpoints"), list):
        _set_agent(run_id, "tracer", "failed")
        why = stream.errors[-1] if stream.errors else "impact.json is missing or not in the expected shape"
        raise StageError(f"the Tracer did not produce impact.json ({why})")
    eps = [e for e in impact["endpoints"] if isinstance(e, dict)]
    loud = sum(1 for e in eps if str(e.get("failure")).lower() == "loud")
    silent = sum(1 for e in eps if str(e.get("failure")).lower() == "silent")
    _set_agent(run_id, "tracer", "done")
    emit(run_id, "S3", "tracer", f"Tracer done: impact.json - {len(eps)} endpoints ({loud} loud, {silent} silent)", "ok")


# --- S4 Transformer ----------------------------------------------------------

def _transformer(ctx: dict, fix: dict | None = None) -> None:
    run_id, run_rel, branch = ctx["run_id"], ctx["run_rel"], ctx["branch"]
    _set_agent(run_id, "transformer", "running", "transformer")
    if fix is not None:  # the Verifier judges the new commit again: its previous verdict no longer stands
        _update(run_id, agents={"verifier": "waiting"}, stages={"verify": "waiting", "verifier": "waiting"},
                verdict=None)
    code, out = _git(ctx, "checkout", "--quiet", branch)
    if code != 0:
        raise StageError(f"could not check out {branch}: {_tail(out)}")
    before = _git(ctx, "rev-parse", "HEAD")[1].strip()
    cons_rel, up_name = ctx["cons_rel"], ctx["up"] or ctx["repo"]
    commit = (f'cd {cons_rel} && git add -A . && git commit -q -m "fix(contract): {{what}} (SyncSnitch {run_id})" '
              f'-m "{_trailer(run_id)}"')
    if fix is None:
        emit(run_id, "S4", "transformer", f"Transformer started on branch {branch}: tolerant reader for v1 + v2")
        prompt = f"""SyncSnitch run {run_id}, step S4. You are Subagent 2, the Downstream Code Transformer, running headless from the SyncSnitch website: never ask questions, keep replies short.
Paths are relative to the workspace root. The consumer {cons_rel} is inside the git clone {ctx['work_rel']}, already on branch {branch}. The upstream {ctx['up_rel']} is read-only.
1. Read {run_rel}/impact.json and apply .bob/rules-syncsnitch-transformer/tolerant-reader.md exactly, with UPSTREAM={ctx['up_rel']}, HEAD_REF={ctx['head_sha']}, BASE_REF={ctx['base_sha']}, UPSTREAM_REPO={ctx['repo']}, PR_NUMBER=null, RUN_ID={run_id}. Edit only files inside {cons_rel}.
2. Run the consumer unit tests until they pass: cd {cons_rel} && uv run pytest -q
3. Commit on {branch}: {commit.format(what=f"tolerant reader for the {up_name} contract change")}
   Do not push.
4. Reply with one line: files changed, insertions, deletions."""
    else:
        emit(run_id, "S4", "transformer", f"Transformer fix round on {branch}: applying the Verifier's instructions")
        failing = [f"{c['id']} {c.get('name', '')}: {c.get('details', '')}"
                   for c in (live._load(ctx["run_dir"] / "verification.json") or {}).get("checks", [])
                   if c.get("status") == "fail"]
        todo = "\n".join(f"- {i}" for i in fix.get("fix_instructions") or [])
        prompt = f"""SyncSnitch run {run_id}, step S4 fix round. You are Subagent 2, the Downstream Code Transformer, running headless from the SyncSnitch website: never ask questions, keep replies short.
Paths are relative to the workspace root. The consumer {cons_rel} is inside the git clone {ctx['work_rel']}, on branch {branch}. The upstream {ctx['up_rel']} is read-only. The rules in .bob/rules-syncsnitch-transformer/tolerant-reader.md still apply.
The Contract Verifier found these failing checks:
{chr(10).join('- ' + f for f in failing) or '- (see the instructions)'}
Apply exactly these fix instructions, editing only files inside {cons_rel}:
{todo}
Then run cd {cons_rel} && uv run pytest -q until green, and commit on {branch}: {commit.format(what="address the Contract Verifier findings")}
Do not push. Reply with one line."""
    stream = _agent(ctx, "transformer", prompt)
    # the branch must hold the work: commit anything the agent left uncommitted (said so in the log)
    pending = _run(["git", "-C", str(ctx["cons_path"]), "status", "--porcelain", "--", "."])[1]
    if pending.strip():
        _run(["git", "-C", str(ctx["cons_path"]), "add", "-A", "."])
        code, out = _run(["git", "-C", str(ctx["cons_path"]), "commit", "-q", "-m",
                          f"chore(syncsnitch): commit the Transformer's remaining edits ({run_id})",
                          "-m", _trailer(run_id)])
        note = (f"The Transformer left edits uncommitted: the runner committed them on {branch}" if code == 0
                else f"Could not commit the Transformer's leftover edits: {_tail(out)}")
        emit(run_id, "S4", "transformer", note, "warn")
    after = _git(ctx, "rev-parse", "HEAD")[1].strip()
    facts = live._transformer_facts(run_id, _spec(run_id))
    ahead = _git(ctx, "rev-list", "--count", f"{ctx['head_sha']}..HEAD")[1].strip()
    if not ahead.isdigit() or int(ahead) == 0:
        _set_agent(run_id, "transformer", "failed")
        why = stream.errors[-1] if stream.errors else "no new commit on the branch"
        raise StageError(f"the Transformer made no changes ({why})")
    if after == before:  # a resumed run whose earlier session already committed, or a fix round with no change
        emit(run_id, "S4", "transformer", "No new commit in this session: " + (
            stream.errors[-1] if stream.errors else "the branch already holds the Transformer's work")
             + ". S5 and the Verifier judge the branch as it is", "warn")
    _set_agent(run_id, "transformer", "done")
    emit(run_id, "S4", "transformer",
         f"Transformer done: {len(facts.get('files') or [])} files, +{facts.get('insertions', 0)} / "
         f"-{facts.get('deletions', 0)} lines, {len(facts.get('commits') or [])} commit(s) on {branch}", "ok")


# --- S5 verify (deterministic) -----------------------------------------------

def _verify(ctx: dict) -> dict:
    run_id = ctx["run_id"]
    _update(run_id, state="verify", agents={"verifier": "running"}, stages={"verify": "running", "verifier": "waiting"})
    _git(ctx, "checkout", "--quiet", ctx["branch"])
    docker = docker_ready()
    _update(run_id, docker=docker)
    if not docker:
        emit(run_id, "S5", "verifier", "Docker is not running on this machine: V3-V5 (mock containers) will be "
                                       "skipped. Start Docker Desktop to run them", "warn")
    vpath = ctx["run_dir"] / "verification.json"
    vpath.unlink(missing_ok=True)
    cmd = [*_engine(), "verify", "--run-id", run_id, "--runs-dir", str(live.RUNS_DIR),
           "--upstream", str(ctx["up_path"]), "--base", ctx["base_sha"], "--head", ctx["head_sha"],
           "--consumer", str(ctx["cons_path"]), "--consumer-base", ctx["head_sha"]]
    if not docker:
        cmd.append("--no-containers")
    code, out = _run(cmd, cwd=REPO_ROOT, timeout=VERIFY_TIMEOUT)
    (ctx["run_dir"] / "verify.log").write_text(out, encoding="utf-8")
    verification = live._load(vpath)
    if not verification or not verification.get("checks"):
        _update(run_id, stages={"verify": "failed"})
        _set_agent(run_id, "verifier", "failed")
        raise StageError(f"S5 verify did not write verification.json (exit {code}): {_tail(out)}")
    _update(run_id, stages={"verify": "done"})
    return verification


# --- S6 Verifier -------------------------------------------------------------

def _verifier(ctx: dict) -> dict:
    run_id, run_rel = ctx["run_id"], ctx["run_rel"]
    _set_agent(run_id, "verifier", "running", "verifier")
    verdict_path = ctx["run_dir"] / "verdict.json"
    verdict_path.unlink(missing_ok=True)
    checks = (live._load(ctx["run_dir"] / "verification.json") or {}).get("checks", [])
    skipped = [c["id"] for c in checks if c.get("status") == "skip"]
    emit(run_id, "S6", "verifier", "Verifier started: judging verification.json")
    prompt = f"""SyncSnitch run {run_id}, step S6. You are Subagent 3, the Contract Verifier, running headless from the SyncSnitch website: never ask questions, never edit code, keep replies short.
Read {run_rel}/verification.json: the deterministic checks V1-V6 of the Transformer's branch {ctx['branch']}{" (Docker was not running, so " + ", ".join(skipped) + " are skipped)" if skipped else ""}.
Write {run_rel}/verdict.json:
{{"run_id": "{run_id}", "verdict": "green|red", "reasons": ["..."], "fix_instructions": ["..."]}}
Rules: the checks are the only truth. Any check with status "fail" makes the verdict red and needs precise, file-level fix_instructions for the Transformer (read {run_rel}/VERIFICATION.md and the failing consumer files under {ctx['cons_rel']} only if you need them). "skip" is not a failure, but name every skipped check in reasons. Green has an empty fix_instructions list.
Reply with one line: the verdict and the first reason."""
    stream = _agent(ctx, "verifier", prompt)
    verdict = live._load(verdict_path)
    failed = [c["id"] for c in checks if c.get("status") == "fail"]
    if not isinstance(verdict, dict) or verdict.get("verdict") not in ("green", "red"):
        why = stream.errors[-1] if stream.errors else "verdict.json is missing or invalid"
        verdict = {"run_id": run_id, "verdict": "red" if failed else "green",
                   "reasons": [f"The Verifier session ended without a verdict ({why}); this verdict is computed by "
                               "the runner from the deterministic checks only."]
                              + ([f"Failing: {', '.join(failed)}"] if failed else [])
                              + ([f"Skipped: {', '.join(skipped)}"] if skipped else []),
                   "fix_instructions": [], "source": "runner"}
        verdict_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        emit(run_id, "S6", "verifier", "No verdict from the Verifier session: the runner computed it from the "
                                       "checks", "warn")
    elif verdict["verdict"] == "green" and failed:  # deterministic checks always win
        verdict["verdict"] = "red"
        verdict.setdefault("reasons", []).insert(0, f"Overridden to red by the runner: {', '.join(failed)} failed")
        verdict_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        emit(run_id, "S6", "verifier", f"The Verifier said GREEN but {', '.join(failed)} failed: overridden to RED "
                                       "(the deterministic checks win)", "warn")
    first = (verdict.get("reasons") or [""])[0]
    _set_agent(run_id, "verifier", "done")
    _update(run_id, verdict=verdict["verdict"])
    emit(run_id, "S6", "verifier", f"Verifier verdict: {verdict['verdict'].upper()}" + (f" - {first}" if first else ""),
         "ok" if verdict["verdict"] == "green" else "warn")
    return verdict


# --- S7 gate, S8 draft PR, S9 artifact ---------------------------------------

def _gate(ctx: dict, verdict: dict) -> None:
    run_id = ctx["run_id"]
    _update(run_id, state="approval", verdict=verdict["verdict"])
    if verdict["verdict"] == "green":
        emit(run_id, "S7", "human", "S7 human approval gate: review the patch, then approve or reject on this page")
    else:
        emit(run_id, "S7", "human", "S7 gate stays closed: the verdict is RED, so no PR can be opened. Reject the "
                                    "run, or fix the branch and start a new run", "warn")


def _publish(run_id: str) -> None:
    ctx = _ctx(run_id)
    run_rel = ctx["run_rel"]
    try:
        head = ctx["head"] or ""
        base_branch = head if head and not SHA_RE.match(head) else (ctx["spec"].get("default_branch") or "main")
        code, out = _run([*_engine(), "report", "--run-id", run_id, "--runs-dir", str(live.RUNS_DIR), "--format", "pr",
                          "--upstream-pr-url", ctx["compare_url"]], cwd=REPO_ROOT, timeout=120)
        body = ctx["run_dir"] / "pr_body.md"
        if code != 0 or not body.exists():
            raise StageError(f"could not write the PR body: {_tail(out)}")
        emit(run_id, "S8", "engine",
             f"S8: pushing {ctx['branch']} and opening a DRAFT companion PR against {base_branch}")
        title = (f"SyncSnitch: make {ctx['cons'] or 'the consumer'} tolerant of the "
                 f"{ctx['up'] or 'upstream'} contract change")
        code, out = _run(["bash", str(REPO_ROOT / "scripts" / "open_companion_pr.sh"), str(ctx["cons_path"]),
                          ctx["branch"], title, str(body), ctx["repo"], "-", base_branch], cwd=REPO_ROOT, timeout=300)
        m = re.search(r"COMPANION_PR_URL=(\S+)", out)
        if code != 0 or not m:
            raise StageError(f"could not open the draft PR: {_tail(out)}")
        url = m.group(1)
        _update(run_id, companion_pr_url=url)
        emit(run_id, "S8", "engine", f"Draft companion PR opened: {url}", "ok")
        code, out = _run([*_engine(), "run-artifact", "--run-id", run_id, "--runs-dir", str(live.RUNS_DIR),
                          "--consumer", str(ctx["cons_path"]), "--branch", ctx["branch"],
                          "--base-branch", ctx["head_sha"], "--upstream-pr-url", ctx["compare_url"],
                          "--companion-pr-url", url, "--bob-export", f"{run_rel}/bob/",
                          "--out-dir", str(live.WEB_RUNS)], cwd=REPO_ROOT, timeout=120)
        if code != 0:
            raise StageError(f"could not write the run artifact: {_tail(out)}")
        _update(run_id, state="complete")
        emit(run_id, "S9", "site", f"Run complete: replay page /runs/{run_id}", "ok")
    except StageError as e:
        _update(run_id, state="publish_failed", error=str(e))
        emit(run_id, "S8", "engine", f"Publishing stopped: {e}. Fix it and press Approve again", "error")
    except Exception as e:  # noqa: BLE001
        _update(run_id, state="publish_failed", error=f"{type(e).__name__}: {e}")
        emit(run_id, "S8", "engine", f"Publishing stopped: {type(e).__name__}: {e}", "error")
