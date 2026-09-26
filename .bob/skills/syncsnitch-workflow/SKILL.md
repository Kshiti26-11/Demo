---
name: syncsnitch-workflow
description: SyncSnitch S0-S9 - detect an upstream contract change (REST, gRPC, DB), trace the consumer, generate a tolerant-reader adapter, verify it with mock containers, ask a human, then open a DRAFT companion PR.
---
# SyncSnitch workflow (S0-S9)

Run every command from the main repo root (`~/hack/syncsnitch`, the kshiti26-11/demo checkout).
Deterministic steps are shell commands: run them exactly, do not re-implement them. Keep messages short.
Artifacts live in `.syncsnitch/runs/<RUN_ID>/`. NEVER edit the upstream.
Progress lines for the website's live run page: run the `syncsnitch log` commands below exactly where shown (0 tokens).

## S0 - prepare (deterministic)
Pick the mode from the first argument, set the variables, then run S1-S9 with them.
Do NOT stop to ask the user any questions before S7. Run automatically through S0 to S6 and wait ONLY at S7 for the human decision.

**Auto mode (Default - when `$1` is empty, omitted, or "auto")**:
Automatic zero-friction demo run:
1. Detect layout and set variables:
   - If `./orders-service` and `./billing-service` exist in the workspace (monorepo):
     UPSTREAM=`orders-service`, CONSUMER=`billing-service`, CONSUMER_BASE=`main`,
     BASE_REF=`15f95af008e5`, HEAD_REF=`HEAD`, PR_NUMBER=`1`, UPSTREAM_REPO=`kshiti26-11/demo`,
     UPSTREAM_URL=`https://github.com/kshiti26-11/demo`, BRANCH=`syncsnitch/orders-service-pr1`
   - If `../orders-service` and `../billing-service` exist (multi-repo):
     UPSTREAM=`../orders-service`, CONSUMER=`../billing-service`, CONSUMER_BASE=`main`,
     BASE_REF=`main`, HEAD_REF=`feat/orders-v2`, PR_NUMBER=`1`, UPSTREAM_REPO=`kshiti26-11/orders-service`,
     UPSTREAM_URL=`https://github.com/kshiti26-11/orders-service`, BRANCH=`syncsnitch/orders-service-pr1`
2. `RUN_ID=r-$(date -u +%Y%m%d-%H%M%S)`; `mkdir -p .syncsnitch && touch .syncsnitch/ACTIVE` (turns write-guard on).
3. Ensure `<CONSUMER>` is ready on clean v1 baseline:
   `git -C <CONSUMER> checkout <CONSUMER_BASE> 2>/dev/null || true`
   `git checkout dd9fff4 -- <CONSUMER> 2>/dev/null || true`
   `git -C <CONSUMER> branch -D <BRANCH> 2>/dev/null || true`
4. Immediately proceed to S1, S2, S3, S4, S5, S6.

**PR mode** - `$1` is a GitHub pull request URL (e.g. https://github.com/kshiti26-11/orders-service/pull/1):
1. `gh pr view <PR_URL> --json number,headRefName,baseRefName` -> PR_NUMBER, HEAD_REF, BASE_REF.
2. `git -C ../orders-service fetch origin` and `git -C ../billing-service checkout main && git -C ../billing-service pull --ff-only`
3. `RUN_ID=r-$(date -u +%Y%m%d-%H%M%S)`; `mkdir -p .syncsnitch && touch .syncsnitch/ACTIVE` (turns the write-guard hook on).
4. UPSTREAM=`../orders-service`, CONSUMER=`$2` or `../billing-service`, CONSUMER_BASE=`main`,
   BRANCH=`syncsnitch/orders-service-pr<PR_NUMBER>`, UPSTREAM_URL=`<PR_URL>`, UPSTREAM_REPO=`kshiti26-11/orders-service`.

**Link mode** - `$1` is a SyncSnitch website link `.../analyze?repo=...&upstream=...&consumer=...&base=...&head=...&run=...`
(the website already ran S1-S2 for that link and waits for this run):
1. Read REPO, UPSTREAM_DIR, CONSUMER_DIR, BASE_REF (=base), HEAD_REF (=head), RUN_ID (=run) from the link's query string
   (URL-decode; an empty folder means the repository root).
2. `W=.syncsnitch/work/<RUN_ID>`; `gh repo clone <REPO> $W` (or `git -C $W fetch origin` if it exists); `git -C $W checkout <HEAD_REF>`.
3. `mkdir -p .syncsnitch && printf '%s\n' "<UPSTREAM_DIR>" > .syncsnitch/ACTIVE` (write guard; protects that folder).
4. UPSTREAM=`$W/<UPSTREAM_DIR>`, CONSUMER=`$W/<CONSUMER_DIR>`, CONSUMER_BASE=`<HEAD_REF>`, BRANCH=`syncsnitch/<RUN_ID>`,
   UPSTREAM_URL=`https://github.com/<REPO>/compare/<BASE_REF>...<HEAD_REF>`, UPSTREAM_REPO=`<REPO>`, PR_NUMBER=`-`.

**Website mode (headless, no Bob IDE step)** - the SyncSnitch website (`web/webapp/agents.py`) is the orchestrator:
someone pastes a GitHub link, the site runs S0-S2, clones the repo into `.syncsnitch/work/<RUN_ID>` on branch
`syncsnitch/<RUN_ID>`, then starts each agent with IBM Bob Shell:
`bob run --mode syncsnitch-tracer|syncsnitch-transformer|syncsnitch-verifier --format stream-json --max-cost <budget share> ...`
with the S3/S4/S6 task text below (paths filled in). The site runs S5, shows S7 on the run page, and runs S8-S9 after the
human approves there. In that mode an agent does only its own step and never asks questions.

## S1 - detect drift (deterministic, 0 tokens)
`uv run syncsnitch detect --upstream <UPSTREAM> --base <BASE_REF> --head <HEAD_REF> --run-id <RUN_ID>`
Success: prints the breaking changes and writes drift.json. If it reports 0 breaking changes: tell the user and stop.

## S2 - trace the consumer (deterministic)
`uv run syncsnitch trace --run-id <RUN_ID> --consumer <CONSUMER>`
Then copy the upstream change proposal for S3:
`git -C <UPSTREAM> show "<HEAD_REF>:./docs/orders-v2-change-proposal.docx" > .syncsnitch/runs/<RUN_ID>/change-proposal.docx || git -C <UPSTREAM> show "origin/<HEAD_REF>:./docs/orders-v2-change-proposal.docx" > .syncsnitch/runs/<RUN_ID>/change-proposal.docx || true`

## S3 - Schema Diff & AST Tracer (AI)
First: `uv run syncsnitch log --run-id <RUN_ID> --step S3 --agent tracer "Tracer started: classifying every traced usage as loud or silent"`
Delegate to a sub-agent / mode `syncsnitch-tracer` with this task:
"Read .syncsnitch/runs/<RUN_ID>/drift.json and candidates.json, the consumer files they point to (under <CONSUMER>), and the
change proposal .syncsnitch/runs/<RUN_ID>/change-proposal.docx if it exists. Write .syncsnitch/runs/<RUN_ID>/impact.json exactly in this shape:
{"run_id": "...", "mapping": [{"change_ids": [...], "old": "total_price", "new": "total.amount_minor", "rule": "..."}],
 "affected": [{"file": "...", "line": 1, "symbol": "...", "change_ids": [...], "surface": "rest|grpc|db|test",
 "failure": "loud|silent|none", "endpoint": "POST /invoices/{order_id}" or null, "fix": "..."}],
 "endpoints": [{"endpoint": "...", "surface": "...", "failure": "loud|silent", "why": "..."}],
 "migration_notes": "3-6 sentences that quote the proposal's rollout and migration guidance"}
Reply with a 5-line summary."
Then: `uv run syncsnitch log --run-id <RUN_ID> --step S3 --agent tracer --level ok "Tracer done: impact.json - <n> endpoints (<loud> loud, <silent> silent)"`

## S4 - Downstream Code Transformer (AI)
First: `uv run syncsnitch log --run-id <RUN_ID> --step S4 --agent transformer "Transformer started on branch <BRANCH>: tolerant reader for v1 + v2"`
Delegate to a sub-agent / mode `syncsnitch-transformer` with this task:
"In <CONSUMER>: `git checkout -b <BRANCH> <CONSUMER_BASE>`. Read .syncsnitch/runs/<RUN_ID>/impact.json and
apply .bob/rules-syncsnitch-transformer/tolerant-reader.md exactly with UPSTREAM=<UPSTREAM>, HEAD_REF=<HEAD_REF>,
UPSTREAM_REPO=<UPSTREAM_REPO>, BASE_REF=<BASE_REF>, PR_NUMBER=<PR_NUMBER>, RUN_ID=<RUN_ID>. Edit only files inside <CONSUMER>.
Unit tests must pass. Commit on the branch. Do not push. Reply with the diffstat."
Then: `uv run syncsnitch log --run-id <RUN_ID> --step S4 --agent transformer --level ok "Transformer done: <diffstat summary>, unit tests green"`

## S5 - verify with mock containers (deterministic; Docker must be running; 2-6 minutes)
`uv run syncsnitch verify --run-id <RUN_ID> --upstream <UPSTREAM> --base <BASE_REF> --head <HEAD_REF> --consumer <CONSUMER> --consumer-base <CONSUMER_BASE>`
Writes verification.json and VERIFICATION.md (checks V1-V6: unit tests, v2 fixtures, containers vs v1, containers vs v2,
Prism contract examples, diff scope).

## S6 - Contract Verifier (AI)
First: `uv run syncsnitch log --run-id <RUN_ID> --step S6 --agent verifier "Verifier started: judging verification.json"`
Delegate to a sub-agent / mode `syncsnitch-verifier` with this task:
"Read .syncsnitch/runs/<RUN_ID>/verification.json. Write .syncsnitch/runs/<RUN_ID>/verdict.json:
{"run_id": "...", "verdict": "green|red", "reasons": [...], "fix_instructions": [...]}. Never edit code.
Deterministic checks are the only truth."
Then: `uv run syncsnitch log --run-id <RUN_ID> --step S6 --agent verifier --level <ok if green, warn if red> "Verifier verdict: <GREEN|RED> - <first reason>"`
If red on the first round: give fix_instructions to the Transformer (S4 on the same branch), then S5 and S6 again.
If still red: stop, show VERIFICATION.md to the user, and ask what to do.

## S7 - human approval gate (interactive, never skip)
First: `uv run syncsnitch log --run-id <RUN_ID> --step S7 --agent human "Waiting for human approval in IBM Bob"`
Show VERIFICATION.md and `git -C <CONSUMER> diff --relative --stat <CONSUMER_BASE>...HEAD`, then ask the user with these choices:
"Approve & open draft PR" / "Show full diff" / "Request changes" / "Abort".
- Show full diff -> `git -C <CONSUMER> diff --relative <CONSUMER_BASE>...HEAD`, then ask again.
- Request changes -> pass the user's words to the Transformer (S4), then S5-S7.
- Abort -> `uv run syncsnitch log --run-id <RUN_ID> --step S7 --agent human --level warn "Aborted by the human"`, `rm -f .syncsnitch/ACTIVE` and stop.
- On approval: `uv run syncsnitch log --run-id <RUN_ID> --step S7 --agent human --level ok "Approved by the human"`

## S8 - open the DRAFT companion PR (deterministic)
1. `uv run syncsnitch report --run-id <RUN_ID> --format pr --upstream-pr-url <UPSTREAM_URL>` (writes pr_body.md)
2. PR mode / Auto mode: `bash scripts/open_companion_pr.sh <CONSUMER> <BRANCH> "SyncSnitch: adapt billing to Orders API v2 (orders-service#<PR_NUMBER>)" .syncsnitch/runs/<RUN_ID>/pr_body.md <UPSTREAM_REPO> <PR_NUMBER>`
   Link mode: `bash scripts/open_companion_pr.sh <CONSUMER> <BRANCH> "SyncSnitch: make <CONSUMER_DIR> tolerant of the <UPSTREAM_DIR> contract change" .syncsnitch/runs/<RUN_ID>/pr_body.md <REPO> - <HEAD_REF>`
3. Read COMPANION_PR_URL from the last output line, then `uv run syncsnitch log --run-id <RUN_ID> --step S8 --agent engine --level ok "Draft companion PR opened: <COMPANION_PR_URL>"`
(Optional: if the user enabled the GitHub MCP server, you may create the draft PR and the upstream comment with it instead.)

## S9 - run artifact and wrap-up (deterministic)
1. `uv run syncsnitch run-artifact --run-id <RUN_ID> --consumer <CONSUMER> --branch <BRANCH> --base-branch <CONSUMER_BASE> --upstream-pr-url <UPSTREAM_URL> --companion-pr-url <COMPANION_PR_URL>`
2. `rm -f .syncsnitch/ACTIVE`
3. Link mode only (the website polls for this file): `git add web/runs/<RUN_ID>.json && git commit -m "run: <RUN_ID>" -m "Bob-Session: <RUN_ID>" && git pull --rebase && git push`
4. Tell the user: companion PR URL, verification summary, the file web/runs/<RUN_ID>.json, and
   "Export this task now to bob_sessions/exports/" (P3-3-hero-run.md for the hero run).
