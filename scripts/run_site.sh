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
cd web
echo "SyncSnitch on http://localhost:$port"
exec "$uvicorn" webapp.main:app --host 127.0.0.1 --port "$port"
