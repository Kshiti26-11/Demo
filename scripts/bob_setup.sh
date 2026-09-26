#!/usr/bin/env bash
# One-time setup so the SyncSnitch website can start the three IBM Bob agents by itself (IBM Bob Shell, headless).
#   1. installs IBM Bob Shell if it is missing (asks first)
#   2. saves your IBM Bob API key in .env.local (gitignored, chmod 600) - typed hidden, never printed
#   3. shows the IBM license files and records your acceptance (only you can accept it)
#   4. runs a one-turn test session (costs a few hundredths of a Bobcoin)
# Usage: bash scripts/bob_setup.sh
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

if ! command -v bob >/dev/null 2>&1; then
  read -r -p "IBM Bob Shell (bob) is not installed. Install it now from bob.ibm.com? [y/N] " yn
  if [[ ! "$yn" =~ ^[Yy]$ ]]; then
    echo "Install it later with: curl -fsSL https://bob.ibm.com/download/bobshell.sh | bash"
    exit 1
  fi
  curl -fsSL https://bob.ibm.com/download/bobshell.sh | bash -s -- --pm npm
fi
say "IBM Bob Shell $(bob --version 2>/dev/null | head -1)"

have_key=""
if [ -f "$env_file" ] && grep -qE '^(export )?BOB_API_KEY=.+' "$env_file"; then
  read -r -p "A Bob API key is already saved in .env.local. Replace it? [y/N] " yn
  [[ "$yn" =~ ^[Yy]$ ]] || have_key=yes
fi
if [ -z "$have_key" ]; then
  say "Create a key: https://bob.ibm.com -> log in -> your subscription instance -> API keys -> Create (type: Inference)"
  read -r -s -p "Paste your IBM Bob API key (hidden): " key
  echo
  if [ -z "$key" ]; then
    echo "No key entered."
    exit 1
  fi
  set_var BOB_API_KEY "$key"
  unset key
  read -r -p "Only for a key of type 'General': paste your team ID (or press Enter to skip): " team
  [ -z "$team" ] || set_var BOB_TEAM_ID "$team"
  echo "Saved to .env.local (gitignored, readable only by you)."
fi

read -r -p "Bobcoin budget per SyncSnitch run [5]: " run_budget
set_var SYNCSNITCH_BOB_BUDGET "${run_budget:-5}"

set -a
# shellcheck disable=SC1090
. "$env_file"
set +a

accept=""
if ! grep -qE '"licenseConsent": *true' "$HOME/.bob/settings/settings.json" 2>/dev/null; then
  say "IBM Bob Shell license"
  bob --show-license || true
  read -r -p "Have you read the IBM license above, and do you accept it? [y/N] " yn
  if [[ ! "$yn" =~ ^[Yy]$ ]]; then
    echo "Not accepted: the agents cannot run headless without it."
    exit 1
  fi
  accept="--accept-license"
fi

say "Testing a headless IBM Bob session (1 turn)..."
tmp="$(mktemp -d)"
team_flag=""
[ -z "${BOB_TEAM_ID:-}" ] || team_flag="--team-id=$BOB_TEAM_ID"
# shellcheck disable=SC2086 # the optional flags are single words or empty
if (cd "$tmp" && bob run $accept $team_flag --trust --max-turns 1 --max-cost 0.2 -- "Reply with the single word OK."); then
  set_var SYNCSNITCH_AGENT_BACKEND bob
  say "IBM Bob Shell works and now runs the agents. Open the SyncSnitch site (bash scripts/run_site.sh), paste a GitHub link, press Run 3 Agents."
else
  say "The test session failed: check the key (and the team ID for a General key), then run this script again."
  exit 1
fi
rm -rf "$tmp"
