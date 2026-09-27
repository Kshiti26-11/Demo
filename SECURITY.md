# Security

SyncSnitch talks to several AI provider APIs (IBM Bob, Gemini, Groq, xAI, Anthropic) and to GitHub. This page is
the checklist for keeping those credentials out of the repository and out of AI assistant logs.

## Where credentials live

| Credential | Lives in | Never in |
|---|---|---|
| `BOB_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `XAI_API_KEY`, `ANTHROPIC_API_KEY` | `.env.local` (gitignored, `chmod 600`), written by `scripts/*_setup.sh` with hidden input | code, commits, chat, run logs |
| `SYNCSNITCH_PUSH_TOKEN` (opens the draft PR from the cloud runner) | a GitHub Actions secret on the runner repo, set by `scripts/cloud_setup.sh` | `.env`, code, commits |
| `GITHUB_TOKEN` (the deployed site starts GitHub Actions) | a Vercel project environment variable | code, commits |
| Your own `gh` login | the GitHub CLI's own credential store | anywhere in this repo |

`.env.example` documents every variable name with a placeholder value; it holds no real credential and is safe to
commit. Copy it if you want a local reference: `cp .env.example .env.local` and fill it by hand, or just run the
matching `scripts/*_setup.sh`, which does the same thing with hidden input.

## `.gitignore` and `.bobignore`

Both exclude `.env`, `.env.local`, `.env.*` (with `.env.example` explicitly un-ignored) and generic secret-shaped
filenames and patterns (`*credential*`, `*secret*`, `*api*key*`, `*.pem`, `*.key`, `id_rsa`, …). `.bobignore` also
keeps IBM Bob and the API-model agents from reading bulky or generated files. Do not remove a pattern from either
file to work around it — add your file elsewhere, or ask before changing the pattern.

## Why this matters here specifically

- The site's agent engines (`web/webapp/llm_agent.py`) are sandboxed: an agent's shell tool is limited to
  `uv run pytest`, the stub generator and git — the API key never reaches a command an agent runs, and it is never
  echoed into a run's log or commit trailer.
- The write-guard hook (`scripts/bob_hooks/guard.py`) blocks writes to secret-looking files while a run is active.
- Commit and run history are public evidence for this hackathon (`bob_sessions/`, `web/runs/`, the live site) — a
  leaked key here is a leaked key in public, immediately.

## If a credential leaks anyway

1. Revoke/rotate it at the provider immediately (Google AI Studio, GroqCloud, xAI, Anthropic Console, or your IBM
   Bob account settings) — don't wait to clean up history first.
2. Remove it from git history (`git filter-repo` or GitHub's own guidance), not just from the latest commit.
3. Re-run the matching `scripts/*_setup.sh` with the new key.
4. If it was a GitHub Actions secret, `gh secret set NAME -R <runner-repo>` with the new value.

## Reporting a vulnerability

This is a hackathon project, not a maintained service. If you find a security issue in the code itself (not a
leaked credential), open an issue or reach the team through the contacts in the root [README](README.md).
