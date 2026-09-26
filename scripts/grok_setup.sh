#!/usr/bin/env bash
# One-time setup so the SyncSnitch website runs the three agents on Grok (xAI API) instead of IBM Bob.
#   1. saves your xAI API key in .env.local (gitignored, chmod 600) - typed hidden, never printed
#   2. picks the model and the token budget per run
#   3. makes Grok the agent engine (SYNCSNITCH_AGENT_BACKEND=grok; bash scripts/bob_setup.sh switches back)
#   4. sends one tiny test request
# Usage: bash scripts/grok_setup.sh
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
if [ -f "$env_file" ] && grep -qE '^(export )?XAI_API_KEY=.+' "$env_file"; then
  read -r -p "An xAI API key is already saved in .env.local. Replace it? [y/N] " yn
  [[ "$yn" =~ ^[Yy]$ ]] || have_key=yes
fi
if [ -z "$have_key" ]; then
  say "Create a key: https://console.x.ai -> API Keys -> Create API key"
  read -r -s -p "Paste your xAI API key (hidden): " key
  echo
  if [ -z "$key" ]; then
    echo "No key entered."
    exit 1
  fi
  set_var XAI_API_KEY "$key"
  unset key
  echo "Saved to .env.local (gitignored, readable only by you)."
fi

say "Model: grok-4.7 (newest, default), grok-4.3 (cheaper), grok-build-0.1 (cheapest)"
read -r -p "Model [grok-4.7]: " model
set_var SYNCSNITCH_GROK_MODEL "${model:-grok-4.7}"
read -r -p "Token budget per SyncSnitch run (input + output, all 3 agents) [3000000]: " run_budget
set_var SYNCSNITCH_TOKEN_BUDGET "${run_budget:-3000000}"
set_var SYNCSNITCH_AGENT_BACKEND grok

say "Testing the key with one tiny request..."
cd "$root"
if .venv/bin/python -m web.webapp.llm_agent grok; then
  say "Grok now runs the agents. Open the SyncSnitch site (bash scripts/run_site.sh), paste a GitHub link, press Run 3 Agents."
else
  say "The test request failed: check the key and the model name, then run this script again."
  exit 1
fi
