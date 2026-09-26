import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import agents, analyze, live
from .matrix import get_matrix
from .tryit import run as run_tryit

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="SyncSnitch demo")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
BOBIDE = shutil.which("bobide") or next(
    (p for p in ["/Applications/IBM Bob.app/Contents/Resources/app/bin/bobide"] if Path(p).exists()), None)


def live_badge(request: Request) -> str:
    """The header badge: where this site is actually serving from."""
    return "LIVE" if live.ON_VERCEL or not request.url.port else f"LIVE :{request.url.port}"


templates.env.globals["live_badge"] = live_badge


def bob_available() -> bool:
    return bool(BOBIDE) and not live.ON_VERCEL


class TryRequest(BaseModel):
    scenario: str


class LaunchRequest(BaseModel):
    link: str
    upstream: str | None = None
    consumer: str | None = None
    base: str | None = None
    head: str | None = None


class VerifyRequest(BaseModel):
    repo: str
    upstream: str
    consumer: str
    base: str
    head: str
    consumer_ref: str | None = None
    run: str


def get_runs_dir() -> Path:
    return live.WEB_RUNS  # web/runs (SYNCSNITCH_WEB_RUNS overrides it)


def load_run(run_id: str) -> dict | None:
    p = get_runs_dir() / f"{run_id}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_runs() -> list[dict]:
    runs_dir = get_runs_dir()
    real_runs = []
    sample_runs = []
    for f in runs_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if f.name.startswith("_"):
                data["is_sample"] = True
                sample_runs.append(data)
            else:
                data["is_sample"] = False
                real_runs.append(data)
        except Exception:
            continue

    real_runs.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return real_runs + sample_runs


def impact_mermaid(run: dict) -> str:
    """Mermaid "graph LR" of the run's impact: breaking change -> consumer file -> endpoint (tests left out)."""
    changes = {c["id"]: c for c in ((run.get("drift") or {}).get("changes") or [])}
    failure = {}
    for e in ((run.get("impact") or {}).get("endpoints") or []):
        failure[e.get("endpoint")] = (e.get("failure") or e.get("severity") or "").upper()
    ids: dict[str, str] = {}
    nodes: list[str] = []

    def node(key: str, label: str) -> str:
        if key not in ids:
            ids[key] = f"N{len(ids)}"
            nodes.append(f'  {ids[key]}["{label.replace(chr(34), chr(39))}"]')
        return ids[key]

    hits = [h for h in ((run.get("candidates") or {}).get("hits") or []) if not h.get("in_tests")]
    surfaces: dict[str, set[str]] = {}  # removed name -> surfaces that removed it
    for hit in hits:
        for cid in hit.get("change_ids") or []:
            surface = (changes.get(cid) or {}).get("surface") or cid.split(":")[0]
            surfaces.setdefault(hit["token"], set()).add({"grpc": "gRPC"}.get(surface, surface.upper()))
    edges: set[tuple[str, str]] = set()
    for hit in hits:
        f = node("f:" + hit["file"], hit["file"])
        tok = hit["token"]
        edges.add((node("t:" + tok, f"{tok} · {'/'.join(sorted(surfaces.get(tok, [])))}"), f))
        for ep in hit.get("endpoints") or []:
            edges.add((f, node("e:" + ep, f"{ep} ({failure[ep]})" if failure.get(ep) else ep)))
    if not edges:
        return ""
    return "\n".join(["graph LR", *nodes, *(f"  {a} --> {b}" for a, b in sorted(edges))])


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="home.html", context={"bob_available": bob_available()})

@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    runs = list_runs()
    return templates.TemplateResponse(request=request, name="runs.html", context={"runs": runs})

@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    run = load_run(run_id)
    if run is None and analyze.valid_run_id(run_id):  # a Bob run pushed after the last deploy
        try:
            run = analyze.bob_artifact(analyze.client(), run_id, get_runs_dir())
        except analyze.AnalyzeError:
            run = None
    if run is None:
        return templates.TemplateResponse(request=request, name="not_found.html", status_code=404)
    return templates.TemplateResponse(
        request=request, name="run_detail.html", context={"run": run, "impact_graph": impact_mermaid(run)}
    )

@app.get("/matrix", response_class=HTMLResponse)
def matrix(request: Request):
    mat = get_matrix()
    return templates.TemplateResponse(request=request, name="matrix.html", context={"matrix": mat})

@app.get("/api/matrix")
def api_matrix():
    return get_matrix()

@app.get("/try", response_class=HTMLResponse)
def try_it(request: Request):
    return templates.TemplateResponse(request=request, name="try.html")

@app.post("/api/try")
def api_try(req: TryRequest):
    try:
        return run_tryit(req.scenario)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/runs")
def api_runs():
    return list_runs()

@app.get("/api/runs/{run_id}")
def api_run_detail(run_id: str):
    run = load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


# --- paste a GitHub repo link -> S1 + S2 live, S3-S9 handed to IBM Bob and GitHub Actions -----------------

def _analysis(request: Request, repo: str, upstream: str | None, consumer: str | None, base: str | None,
              head: str | None, consumer_ref: str | None, run: str | None) -> dict:
    gh = analyze.client()
    found, commits, chosen = analyze.resolve(gh, repo, upstream, consumer, base, head)
    upstream, consumer, base, head = chosen["upstream"], chosen["consumer"], chosen["base"], chosen["head"]
    run = run if analyze.valid_run_id(run or "") else analyze.new_run_id()
    result = analyze.run_pipeline(gh, found["repo"], upstream, consumer, base, head, consumer_ref)
    params = {"repo": found["repo"], "upstream": upstream, "consumer": consumer, "base": result["base_sha"][:12],
              "head": head, "run": run}
    if consumer_ref and consumer_ref != head:
        params["consumer_ref"] = consumer_ref
    link = f"{str(request.base_url).rstrip('/')}/analyze?{urlencode(params)}"
    graph = impact_mermaid({"drift": {"changes": result["changes"]}, "candidates": {"hits": result["hits"]}})
    return {"found": found, "commits": commits, "result": result, "run_id": run, "link": link,
            "bob_command": f"/syncsnitch {link}", "impact_graph": graph,
            "actions_enabled": gh.has_token, "home_repo": analyze.HOME_REPO}


@app.get("/analyze", response_class=HTMLResponse)
def analyze_page(request: Request, repo: str = "", upstream: str | None = None, consumer: str | None = None,
                 base: str | None = None, head: str | None = None, consumer_ref: str | None = None,
                 run: str | None = None):
    ctx: dict = {"repo_input": repo}
    if repo:
        try:
            ctx.update(_analysis(request, repo, upstream, consumer, base, head, consumer_ref, run))
        except analyze.AnalyzeError as e:
            ctx["error"] = str(e)
    return templates.TemplateResponse(request=request, name="analyze.html", context=ctx,
                                      status_code=400 if ctx.get("error") else 200)


@app.get("/api/analyze")
def api_analyze(request: Request, repo: str, upstream: str | None = None, consumer: str | None = None,
                base: str | None = None, head: str | None = None, consumer_ref: str | None = None,
                run: str | None = None):
    try:
        data = _analysis(request, repo, upstream, consumer, base, head, consumer_ref, run)
    except analyze.AnalyzeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data["found"].pop("paths", None)
    return data


@app.post("/api/analyze/verify")
def api_analyze_verify(req: VerifyRequest):
    """S5 in GitHub Actions: Docker mock containers, consumer vs upstream v1 and v2."""
    if not analyze.valid_run_id(req.run):
        raise HTTPException(status_code=400, detail="bad run id")
    gh = analyze.client()
    if not gh.has_token:
        raise HTTPException(status_code=503, detail="set GITHUB_TOKEN on the server to start GitHub Actions runs")
    try:
        analyze.parse_repo_url(req.repo)
        gh.dispatch({"repo": req.repo, "upstream": req.upstream, "consumer": req.consumer, "base": req.base,
                     "head": req.head, "consumer_ref": req.consumer_ref or req.head, "run_id": req.run})
    except analyze.AnalyzeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"started": True, "actions_url": f"https://github.com/{analyze.HOME_REPO}/actions/workflows/{analyze.WORKFLOW}"}


@app.get("/api/analyze/status")
def api_analyze_status(run: str):
    """Progress of S3-S9: the Bob run artifact (web/runs/<run>.json) and the Actions container run."""
    if not analyze.valid_run_id(run):
        raise HTTPException(status_code=400, detail="bad run id")
    gh = analyze.client()
    status: dict = {"run": run, "bob": None, "actions": None}
    try:
        art = analyze.bob_artifact(gh, run, get_runs_dir())
        if art:
            status["bob"] = {"steps": art.get("steps"), "companion_pr_url": art.get("companion_pr_url"),
                             "verdict": (art.get("verdict") or {}).get("verdict"), "url": f"/runs/{run}"}
        if gh.has_token:
            wf = gh.find_run(run)
            if wf:
                status["actions"] = {"status": wf["status"], "conclusion": wf.get("conclusion"),
                                     "html_url": wf["html_url"]}
                if wf["status"] == "completed":
                    status["actions"]["verification"] = gh.run_verification(wf)
    except analyze.AnalyzeError as e:
        status["error"] = str(e)
    return status


# --- "Run 3 Agents": the live multi-agent run page ----------------------------------------------------------

def _site_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _launch(request: Request, req: LaunchRequest) -> str:
    overrides = {k: getattr(req, k) for k in ("upstream", "consumer", "base", "head") if getattr(req, k) is not None}
    run_id = live.launch(req.link, _site_url(request), overrides)
    return live.live_url(run_id, req.link.strip(), overrides)


@app.post("/api/launch")
def api_launch(request: Request, req: LaunchRequest):
    try:
        url = _launch(request, req)
    except analyze.AnalyzeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"url": url, "run_id": url.split("/")[2].split("?")[0]}


@app.post("/launch")
async def launch_form(request: Request):
    """No-JavaScript fallback for the home page form."""
    # a plain urlencoded body (no python-multipart dependency needed)
    link = (parse_qs((await request.body()).decode("utf-8", "replace")).get("link") or [""])[0]
    try:
        url = _launch(request, LaunchRequest(link=link))
    except analyze.AnalyzeError as e:
        return templates.TemplateResponse(request=request, name="home.html", status_code=400,
                                          context={"launch_error": str(e), "link_input": link,
                                                   "bob_available": bob_available()})
    return RedirectResponse(url, status_code=303)


def _live_query(request: Request) -> dict:
    return {k: request.query_params.get(k) for k in ("link", "upstream", "consumer", "base", "head")}


@app.get("/live/{run_id}", response_class=HTMLResponse)
def live_page(request: Request, run_id: str):
    try:
        known = live.ensure(run_id, _live_query(request), _site_url(request))
    except analyze.AnalyzeError:
        known = False
    if not known:
        return templates.TemplateResponse(request=request, name="not_found.html", status_code=404)
    return templates.TemplateResponse(request=request, name="home.html",
                                      context={"run_id": run_id, "query": request.url.query,
                                               "link_input": request.query_params.get("link"),
                                               "bob_available": bob_available()})


@app.get("/api/live/{run_id}")
def api_live(request: Request, run_id: str):
    try:
        live.ensure(run_id, _live_query(request), _site_url(request))
        st = live.state(run_id)
    except analyze.AnalyzeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if st is None:
        raise HTTPException(status_code=404, detail="run not found")
    return JSONResponse(st, headers={"Cache-Control": "no-store"})


@app.post("/api/live/{run_id}/verify")
def api_live_verify(run_id: str):
    """S5 in GitHub Actions for this run (Docker mock containers); the page picks up the result."""
    st = live.state(run_id) if analyze.valid_run_id(run_id) else None
    if st is None or not st["spec"].get("base_sha"):
        raise HTTPException(status_code=404, detail="run not found or not traced yet")
    gh = analyze.client()
    if not gh.has_token:
        raise HTTPException(status_code=503, detail="set GITHUB_TOKEN on the server to start GitHub Actions runs")
    sp = st["spec"]
    consumer_ref = sp["head"]
    try:  # Bob's fix branch, once S8 has pushed it; before that, the unfixed consumer (proves the break)
        gh.resolve(sp["repo"], f"syncsnitch/{run_id}")
        consumer_ref = f"syncsnitch/{run_id}"
    except analyze.AnalyzeError:
        pass
    try:
        gh.dispatch({"repo": sp["repo"], "upstream": sp["upstream"], "consumer": sp["consumer"], "base": sp["base_sha"],
                     "head": sp["head"], "consumer_ref": consumer_ref, "run_id": run_id})
    except analyze.AnalyzeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    live.emit(run_id, "S5", "verifier", f"S5 containers dispatched to GitHub Actions for consumer {consumer_ref}")
    return {"started": True}


@app.get("/api/live/{run_id}/diff")
def api_live_diff(request: Request, run_id: str):
    try:
        live.ensure(run_id, _live_query(request), _site_url(request))
        return JSONResponse({"diff": live.diff_text(run_id)}, headers={"Cache-Control": "no-store"})
    except analyze.AnalyzeError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _runner_action(run_id: str, action) -> dict:
    if not analyze.valid_run_id(run_id) or live.state(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        action(run_id)
    except agents.StageError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True}


def _start_agents(run_id: str) -> None:
    if not agents.start(run_id):
        problems = agents.runner_status()["problems"]
        raise agents.StageError(problems[0]["text"] + " Fix: " + problems[0]["fix"] if problems
                                else "the agents are already running or this run is past them")


@app.post("/api/live/{run_id}/agents")
def api_live_agents(run_id: str):
    """Start the IBM Bob agents for a traced run, or resume one that stopped (e.g. after fixing the setup)."""
    return _runner_action(run_id, _start_agents)


@app.post("/api/live/{run_id}/approve")
def api_live_approve(run_id: str):
    """S7 approved on the page: the runner opens the DRAFT companion PR (S8) and writes the run artifact (S9)."""
    return _runner_action(run_id, agents.approve)


@app.post("/api/live/{run_id}/reject")
def api_live_reject(run_id: str):
    return _runner_action(run_id, agents.reject)


@app.get("/api/runner")
def api_runner():
    """Can this server run the three IBM Bob agents by itself (Bob Shell, API key, license, Docker)?"""
    return agents.runner_status()


@app.post("/api/open-bob")
def api_open_bob():
    """Local only: bring the IBM Bob IDE with this workspace to the front, for the manual /syncsnitch fallback
    when this machine cannot run the agents headless."""
    if not bob_available():
        raise HTTPException(status_code=503, detail="IBM Bob is not available on this server")
    subprocess.Popen([BOBIDE, str(live.REPO_ROOT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"opened": True}
