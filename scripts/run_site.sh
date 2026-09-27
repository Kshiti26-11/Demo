#!/usr/bin/env bash
# Start the SyncSnitch website locally. Locally it is also the runner: after S1-S2 it starts the three IBM Bob
# agents headless (IBM Bob Shell), runs S5 verify, and opens the draft PR after you approve on the run page.
# Usage: bash scripts/run_site.sh [port]   (default 8000; one-time setup: bash scripts/bob_setup.sh)
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
port="${1:-${PORT:-8000}}"
cd "$root"
venvbin="$root/.venv/bin"; [ -d "$venvbin" ] || venvbin="$root/.venv/Scripts"  # uv on Windows uses Scripts/, not bin/
uvicorn="$venvbin/uvicorn"; [ -e "$uvicorn" ] || uvicorn="$uvicorn.exe"
[ -e "$uvicorn" ] || uv sync --frozen
if command -v docker >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then  # V3-V5 need a running Docker engine
  if command -v colima >/dev/null 2>&1; then hint="colima start"; else hint="start Docker Desktop"; fi
  echo "Docker is installed but not running: V3-V5 (mock containers) will be skipped. To run them: $hint"
fi
cd web
echo "SyncSnitch on http://localhost:$port"
exec "$uvicorn" webapp.main:app --host 127.0.0.1 --port "$port"
