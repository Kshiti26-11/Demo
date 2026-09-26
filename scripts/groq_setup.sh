#!/usr/bin/env bash
# One-time setup so the SyncSnitch website runs the three agents on Groq (GroqCloud API, free tier) instead of IBM Bob.
#   1. saves your Groq API key in .env.local (gitignored, chmod 600) - typed hidden, never printed
#   2. picks the model and the token budget per run
#   3. makes Groq the agent engine (SYNCSNITCH_AGENT_BACKEND=groq; bash scripts/bob_setup.sh switches back)
#   4. sends one tiny test request
# Usage: bash scripts/groq_setup.sh
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
if [ -f "$env_file" ] && grep -qE '^(export )?GROQ_API_KEY=.+' "$env_file"; then
  read -r -p "A Groq API key is already saved in .env.local. Replace it? [y/N] " yn
  [[ "$yn" =~ ^[Yy]$ ]] || have_key=yes
fi
if [ -z "$have_key" ]; then
  say "Create a key: https://console.groq.com/keys -> Create API Key (free tier)"
  read -r -s -p "Paste your Groq API key (hidden): " key
  echo
  if [ -z "$key" ]; then
    echo "No key entered."
    exit 1
  fi
  set_var GROQ_API_KEY "$key"
  unset key
  echo "Saved to .env.local (gitignored, readable only by you)."
fi

say "Model: llama-3.1-8b-instant (default; fast, broadly available on the free tier). Larger models such as"
say "llama-3.3-70b-versatile or openai/gpt-oss-120b need identity verification the free tier may not have -"
say "check what your account can use at https://console.groq.com/playground"
read -r -p "Model [llama-3.1-8b-instant]: " model
set_var SYNCSNITCH_GROQ_MODEL "${model:-llama-3.1-8b-instant}"
read -r -p "Token budget per SyncSnitch run (input + output, all 3 agents) [3000000]: " run_budget
set_var SYNCSNITCH_TOKEN_BUDGET "${run_budget:-3000000}"
set_var SYNCSNITCH_AGENT_BACKEND groq

say "Testing the key with one tiny request..."
cd "$root"
venvbin="$root/.venv/bin"; [ -d "$venvbin" ] || venvbin="$root/.venv/Scripts"  # uv on Windows uses Scripts/, not bin/
python="$venvbin/python"; [ -e "$python" ] || python="$python.exe"
if "$python" -m web.webapp.llm_agent groq; then
  say "Groq now runs the agents. Open the SyncSnitch site (bash scripts/run_site.sh), paste a GitHub link, press Run 3 Agents."
else
  say "The test request failed: check the key and the model name, then run this script again."
  exit 1
fi
