#!/usr/bin/env bash
# One-time setup so the SyncSnitch website runs the three agents on Gemini (Google AI Studio API, free tier) instead of IBM Bob.
#   1. saves your Gemini API key in .env.local (gitignored, chmod 600) - typed hidden, never printed
#   2. picks the model and the token budget per run
#   3. makes Gemini the agent engine (SYNCSNITCH_AGENT_BACKEND=gemini; bash scripts/bob_setup.sh switches back)
#   4. sends one tiny test request
# Usage: bash scripts/gemini_setup.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
env_file="$root/.env.local"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
set_var() { # <name> <value>: replace or add NAME=value in .env.local
  touch "$env_file"
  chmod 600 "$env_file"
  { grep -vE "^(export )?$1=" "$env_file" || true; printf '%s=%s\n' "$1" "$2"; } > "$env_file.tmp"
  mv "$env_file.tmp" "$env_file"
  chmod 600 "$env_file"
}

have_key=""
if [ -f "$env_file" ] && grep -qE '^(export )?GEMINI_API_KEY=.+' "$env_file"; then
  read -r -p "A Gemini API key is already saved in .env.local. Replace it? [y/N] " yn
  [[ "$yn" =~ ^[Yy]$ ]] || have_key=yes
fi
if [ -z "$have_key" ]; then
  say "Create a key: https://aistudio.google.com/apikey -> Create API key (free; free-tier prompts may be used by Google to improve its products)"
  read -r -s -p "Paste your Gemini API key (hidden): " key
  echo
  if [ -z "$key" ]; then
    echo "No key entered."
    exit 1
  fi
  set_var GEMINI_API_KEY "$key"
  unset key
  echo "Saved to .env.local (gitignored, readable only by you)."
fi

say "Model: gemini-3.8-flash (newest Flash, default) or gemini-3.5-flash-lite (lighter; free-tier limits are often higher)"
read -r -p "Model [gemini-3.8-flash]: " model
set_var SYNCSNITCH_GEMINI_MODEL "${model:-gemini-3.8-flash}"
read -r -p "Token budget per SyncSnitch run (input + output, all 3 agents) [3000000]: " run_budget
set_var SYNCSNITCH_TOKEN_BUDGET "${run_budget:-3000000}"
set_var SYNCSNITCH_AGENT_BACKEND gemini

say "Testing the key with one tiny request..."
cd "$root"
venvbin="$root/.venv/bin"; [ -d "$venvbin" ] || venvbin="$root/.venv/Scripts"  # uv on Windows uses Scripts/, not bin/
python="$venvbin/python"; [ -e "$python" ] || python="$python.exe"
if "$python" -m web.webapp.llm_agent gemini; then
  say "Gemini now runs the agents. Open the SyncSnitch site (bash scripts/run_site.sh), paste a GitHub link, press Run 3 Agents."
else
  say "The test request failed: check the key and the model name, then run this script again."
  exit 1
fi
