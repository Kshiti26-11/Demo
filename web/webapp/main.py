import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .matrix import get_matrix
from .tryit import run as run_tryit

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="SyncSnitch demo")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

class TryRequest(BaseModel):
    scenario: str

def get_runs_dir() -> Path:
    return BASE_DIR / "runs"

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
    if real_runs:
        return real_runs
    return sample_runs

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="home.html")

@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    runs = list_runs()
    return templates.TemplateResponse(request=request, name="runs.html", context={"runs": runs})

@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    run = load_run(run_id)
    if run is None:
        return templates.TemplateResponse(request=request, name="not_found.html", status_code=404)
    return templates.TemplateResponse(request=request, name="run_detail.html", context={"run": run})

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
