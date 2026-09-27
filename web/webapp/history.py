"""Every real SyncSnitch run, wherever it lives, for Case files (/runs) and The lineup (/matrix):

  published   web/runs/<run_id>.json          the S9 replay of an approved run (bundled with the site)
  cloud       syncsnitch-live/<run_id>        the cloud runner's snapshot branch (any state: running, red, waiting)
  local       .syncsnitch/runs/<run_id>/      this machine's run folder (the laptop runner)

A run found in several places is one row; the published replay wins for the details page."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import analyze, cloud, live

_RUN_RE = re.compile(r"^w-\d{8}-\d{6}-[0-9a-f]{4}$")
LIVE_SOURCES = True  # read the cloud runner and this machine's run folders (the tests switch it off)
PHASES = {"approval": "Waiting for you", "published": "PR opened", "complete": "PR opened", "rejected": "Rejected", "failed": "Stopped",
          "active": "Running", "traced": "Running", "blocked": "Needs setup"}


def _checks(verification: dict | None) -> list[dict]:
    return [{"id": c.get("id"), "status": c.get("status"), "details": c.get("details")}
            for c in (verification or {}).get("checks") or [] if isinstance(c, dict)]


def _verdict(v) -> str | None:
    v = v.get("verdict") if isinstance(v, dict) else v
    return v if v in ("green", "red") else None


def _row(run_id: str, **kw) -> dict:
    row = {"run_id": run_id, "created_at": "", "repo": "", "link": "", "verdict": None, "phase": "", "status": "",
           "engine": "", "tokens": None, "companion_pr_url": None, "upstream_url": None, "checks": [],
           "details_url": f"/runs/{run_id}", "source": "", "is_sample": False}
    row.update({k: v for k, v in kw.items() if v is not None})
    spent = row["tokens"]  # a number, or per agent in older run folders
    spent = sum(v for v in spent.values() if isinstance(v, (int, float))) if isinstance(spent, dict) else spent
    row["tokens"] = spent if isinstance(spent, (int, float)) and spent > 0 else None
    row["status"] = PHASES.get(row["phase"], row["phase"].capitalize() if row["phase"] else "")
    return row


def _compare_url(spec: dict) -> str | None:
    repo, base, head = spec.get("repo"), spec.get("base_sha") or spec.get("base"), spec.get("head")
    return f"https://github.com/{repo}/compare/{str(base)[:12]}...{head}" if repo and base and head else None


def _live_url(run_id: str, spec: dict) -> str:
    over = {k: spec.get(k) for k in ("upstream", "consumer") if spec.get(k)}
    return live.live_url(run_id, spec.get("link") or f"https://github.com/{spec.get('repo', '')}", over)


def _published() -> dict[str, dict]:
    out = {}
    for f in sorted(live.WEB_RUNS.glob("w-*.json")):
        d = live._load(f)
        if not isinstance(d, dict) or not _RUN_RE.match(str(d.get("run_id") or "")):
            continue
        out[d["run_id"]] = _row(d["run_id"], created_at=d.get("created_at") or "", verdict=_verdict(d.get("verdict")),
                                phase="published" if d.get("companion_pr_url") else "", source="published",
                                companion_pr_url=d.get("companion_pr_url"), upstream_url=d.get("upstream_pr_url"),
                                checks=_checks(d.get("verification")))
    return out


def _from_state(run_id: str, st: dict, source: str) -> dict:
    spec, runner, verifier = st.get("spec") or {}, st.get("runner") or {}, st.get("verifier") or {}
    engine = " ".join(x for x in (runner.get("label"), runner.get("model")) if x)
    return _row(run_id, created_at=spec.get("created_at") or "", repo=spec.get("repo") or "",
                link=spec.get("link") or "", verdict=_verdict(verifier.get("verdict") or runner.get("verdict")),
                phase=st.get("phase") or runner.get("state") or "", engine=engine, tokens=runner.get("spent"),
                companion_pr_url=st.get("companion_pr_url"), upstream_url=_compare_url(spec),
                checks=[c for c in verifier.get("checks") or [] if isinstance(c, dict)],
                details_url=st.get("replay_url") or _live_url(run_id, spec), source=source)


def _cloud() -> dict[str, dict]:
    out = {}
    for run_id in cloud.live_run_ids():
        st = cloud.remote_state(run_id, ttl=60)
        if isinstance(st, dict):
            out[run_id] = _from_state(run_id, st, "cloud")
    return out


def _local() -> dict[str, dict]:
    out = {}
    if live.ON_VERCEL:
        return out
    for d in sorted(live.RUNS_DIR.glob("w-*")):
        spec = live._load(d / "spec.json")
        if not isinstance(spec, dict) or not _RUN_RE.match(d.name):
            continue
        runner = spec.get("runner") or {}
        engine = " ".join(x for x in (runner.get("label") or runner.get("backend"), runner.get("model")) if x)
        created = spec.get("created_at") or spec.get("traced_at") or ""
        out[d.name] = _row(d.name, created_at=created, repo=spec.get("repo") or "", link=spec.get("link") or "",
                           verdict=_verdict(live._load(d / "verdict.json")),
                           phase=runner.get("state") or spec.get("status") or "", engine=engine,
                           tokens=runner.get("spent"), companion_pr_url=spec.get("companion_pr_url"),
                           upstream_url=_compare_url(spec), checks=_checks(live._load(d / "verification.json")),
                           details_url=_live_url(d.name, spec), source="local")
    return out


def all_runs() -> list[dict]:
    """Every real run, newest first. A published replay keeps its /runs page but takes the live state's extras."""
    rows: dict[str, dict] = {}
    for source in ((_local, _cloud) if LIVE_SOURCES else ()) + (_published,):
        try:
            found = source()
        except Exception:  # noqa: BLE001 - one unreachable source must not empty the page
            found = {}
        for run_id, row in found.items():
            old = rows.get(run_id)
            if old and source is _published:
                row = {**old, **{k: v for k, v in row.items() if v not in (None, "", [])}}
            elif old:
                row = {**row, **{k: v for k, v in old.items() if v not in (None, "", [])}}
            rows[run_id] = row
    return sorted(rows.values(), key=lambda r: r["created_at"] or r["run_id"][2:17], reverse=True)


# --- one run in depth: what The lineup shows -------------------------------------------------------------------

def _junit(text: str | None) -> list[dict]:
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out = []
    for tc in root.iter("testcase"):
        bad = tc.find("failure")
        bad = bad if bad is not None else tc.find("error")
        skip = tc.find("skipped") is not None
        msg = " ".join((bad.get("message") or bad.text or "").split())[:240] if bad is not None else ""
        out.append({"name": tc.get("name"), "status": "fail" if bad is not None else "skip" if skip else "pass",
                    "message": msg})
    return out


def run_data(run_id: str) -> dict | None:
    """drift, impact, verification and the per-test container results of one run, from wherever it lives."""
    if not _RUN_RE.match(run_id or ""):
        return None
    local_dir = live.RUNS_DIR / run_id
    published = live._load(live.WEB_RUNS / f"{run_id}.json") or {}
    data = {"run_id": run_id, "drift": published.get("drift"), "impact": published.get("impact"),
            "verification": published.get("verification"), "junit": {}}
    if LIVE_SOURCES and local_dir.is_dir():
        for key in ("drift", "impact", "verification"):
            data[key] = data[key] or live._load(local_dir / f"{key}.json")
        for ver in ("v1", "v2"):
            f = local_dir / "results" / f"junit-{ver}.xml"
            data["junit"][ver] = _junit(f.read_text(encoding="utf-8")) if f.is_file() else []
    if LIVE_SOURCES and (cloud.enabled() or not local_dir.is_dir()):
        for key in ("drift", "impact", "verification"):
            if not data[key]:
                text = cloud.remote_file(run_id, f"run/{key}.json", ttl=60)
                try:
                    data[key] = json.loads(text) if text else None
                except ValueError:
                    data[key] = None
        for ver in ("v1", "v2"):
            if not data["junit"].get(ver):
                data["junit"][ver] = _junit(cloud.remote_file(run_id, f"run/results/junit-{ver}.xml", ttl=60))
    return data if any(data[k] for k in ("drift", "impact", "verification")) else None


def lineup(run_id: str | None = None) -> dict:
    """The lineup of one real run (the newest one whose containers ran, unless run_id picks another):
    billing before / after the fix x orders v1 / v2, every cell from that run's own results."""
    runs = [r for r in all_runs() if r["checks"]]
    ran = [r for r in runs if any(c["id"] in ("V3", "V4") and c["status"] in ("pass", "fail") for c in r["checks"])]
    pick = next((r for r in runs if r["run_id"] == run_id), None) or (ran or runs or [None])[0]
    if pick is None:
        return {"run": None, "runs": []}
    data = run_data(pick["run_id"]) or {}
    changes = [c for c in (data.get("drift") or {}).get("changes") or [] if c.get("breaking")]
    by_surface: dict[str, int] = {}
    for c in changes:
        by_surface[c.get("surface")] = by_surface.get(c.get("surface"), 0) + 1
    endpoints = [e for e in (data.get("impact") or {}).get("endpoints") or [] if isinstance(e, dict)]
    checks = {c["id"]: c for c in _checks(data.get("verification")) or pick["checks"]}

    def after(check_id: str, ver: str) -> dict:
        c = checks.get(check_id) or {}
        status = {"pass": "clean", "fail": "broken"}.get(c.get("status"), "skipped")
        return {"status": status, "details": c.get("details") or "not run", "tests": data.get("junit", {}).get(ver) or []}

    return {
        "run": pick, "runs": runs,
        "breaking": len(changes), "by_surface": by_surface,
        "before": {
            "v1": {"status": "clean", "details": "The contract this consumer was written for: S1 found no change "
                                                 "at the base commit.", "tests": []},
            "v2": {"status": "broken" if changes else "clean",
                   "details": (f"S1 found {len(changes)} breaking changes ("
                               + ", ".join(f"{('gRPC' if s == 'grpc' else s.upper())} {n}" for s, n in by_surface.items())
                               + f"); S2 + the Tracer: {len(endpoints)} endpoints break.") if changes
                   else "S1 found no breaking change.",
                   "endpoints": endpoints, "tests": []},
        },
        "after": {"v1": after("V3", "v1"), "v2": after("V4", "v2")},
    }
