#!/usr/bin/env bash
# One-time setup of the cloud runner: the deployed site (Vercel) then runs the 3 agents on GitHub Actions, with no
# machine of yours switched on (web/webapp/cloud.py, .github/workflows/syncsnitch-agents.yml).
#   1. creates the runner repo (default: <your GitHub user>/syncsnitch-runner, public: Actions minutes are free) and
#      puts the workflow on its main branch
#   2. copies your engine key(s) and SYNCSNITCH_* settings from .env / .env.local into its GitHub Actions secrets
#      (values go straight from the file to GitHub, never onto the screen); asks for a Gemini key if there is none
#   3. stores your GitHub login token as SYNCSNITCH_PUSH_TOKEN, so the runner can open the draft PR after you approve
#   4. tells you the one Vercel setting to add (GITHUB_TOKEN) and opens the token page
# Usage: bash scripts/cloud_setup.sh [owner/runner-repo]      Re-run it any time: it only updates.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
command -v gh >/dev/null || { echo "Install the GitHub CLI first: brew install gh (then: gh auth login)"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Log in to GitHub first: gh auth login"; exit 1; }
me="$(gh api user --jq .login)"
runner="${1:-${SYNCSNITCH_RUNNER_REPO:-$me/syncsnitch-runner}}"
py="$root/.venv/bin/python"; [ -x "$py" ] || py="$root/.venv/Scripts/python.exe"
[ -x "$py" ] || { uv sync --frozen >/dev/null; py="$root/.venv/bin/python"; }

echo "== 1/4 runner repo $runner"
if ! gh repo view "$runner" >/dev/null 2>&1; then
  gh repo create "$runner" --public --description "SyncSnitch cloud runner: the 3 agents on GitHub Actions for the demo site"
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
git clone --quiet "https://github.com/$runner.git" "$tmp/r" 2>/dev/null || git init --quiet "$tmp/r"
mkdir -p "$tmp/r/.github/workflows"
cp .github/workflows/syncsnitch-agents.yml "$tmp/r/.github/workflows/"
cat > "$tmp/r/README.md" <<EOF
# SyncSnitch cloud runner

GitHub Actions runner for the SyncSnitch demo site (code: https://github.com/Kshiti26-11/Demo).
The site dispatches \`syncsnitch-agents.yml\`; each job runs the three agents and pushes the live state of the run
to the branch \`syncsnitch-live/<run_id>\`, which the site shows. Set up by \`bash scripts/cloud_setup.sh\`.
EOF
(
  cd "$tmp/r"
  git checkout --quiet -B main
  git add -A
  if ! git diff --cached --quiet; then
    git -c user.name="$me" -c user.email="$me@users.noreply.github.com" commit --quiet -m "SyncSnitch cloud runner workflow"
    git push --quiet -u "https://github.com/$runner.git" main
    echo "   workflow pushed to $runner (main)"
  else
    echo "   workflow already up to date"
  fi
)

echo "== 2/4 engine key(s) and settings -> GitHub Actions secrets of $runner"
status=0
RUNNER="$runner" "$py" - <<'EOF' || status=$?
import os, subprocess, sys
sys.path.insert(0, ".")
from web.webapp.agents import local_env
env = local_env()
names = ["GEMINI_API_KEY", "GROQ_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY", "SYNCSNITCH_AGENT_BACKEND",
         "SYNCSNITCH_TOKEN_BUDGET", "SYNCSNITCH_GEMINI_MODEL", "SYNCSNITCH_GEMINI_FALLBACK_MODELS",
         "SYNCSNITCH_GROQ_MODEL", "SYNCSNITCH_GROQ_FALLBACK_MODELS", "SYNCSNITCH_GROK_MODEL", "SYNCSNITCH_CLAUDE_MODEL"]
done = []
for name in names:
    if env.get(name):
        subprocess.run(["gh", "secret", "set", name, "--repo", os.environ["RUNNER"]], input=env[name], text=True,
                       check=True, capture_output=True)
        done.append(name)
print("   set: " + (", ".join(done) or "nothing"))
keys = [n for n in done if n.endswith("_API_KEY")]
sys.exit(0 if keys else 3)
EOF
[ "$status" -eq 0 ] || [ "$status" -eq 3 ] || { echo "   Could not set the secrets (see above)."; exit 1; }
if [ "$status" -eq 3 ]; then
  echo "   No engine key found in .env / .env.local. Paste a free Gemini key (https://aistudio.google.com/apikey)."
  read -rsp "   GEMINI_API_KEY (hidden): " key; echo
  [ -n "$key" ] || { echo "   No key: the agents cannot run. Re-run this script with a key."; exit 1; }
  printf '%s' "$key" | gh secret set GEMINI_API_KEY --repo "$runner"
  unset key
  echo "   set: GEMINI_API_KEY"
fi

echo "== 3/4 SYNCSNITCH_PUSH_TOKEN (draft PR after you approve)"
gh auth token | gh secret set SYNCSNITCH_PUSH_TOKEN --repo "$runner"
echo "   set from your gh login ($me)"

echo "== 4/4 Vercel (one setting, then Redeploy)"
url="https://github.com/settings/personal-access-tokens/new?name=SyncSnitch+Vercel&description=Starts+the+SyncSnitch+cloud+runner&expires_in=90&actions=write&contents=read"
cat <<EOF
   a) Create a fine-grained token (the page opens now):
        Repository access: Only select repositories -> $runner
        Permissions: Actions = Read and write, Contents = Read-only (Metadata is added automatically)
   b) Vercel -> the demo project -> Settings -> Environment Variables -> add
        GITHUB_TOKEN = <that token>   (Production + Preview)
EOF
[ "$runner" = "Cybverse-Pkians/syncsnitch-runner" ] || echo "        SYNCSNITCH_RUNNER_REPO = $runner"
cat <<EOF
   c) Deployments -> the latest -> Redeploy.
   Then paste any repo link on the site: the agents run on GitHub Actions (https://github.com/$runner/actions).
EOF
command -v open >/dev/null && open "$url" || echo "   Token page: $url"
