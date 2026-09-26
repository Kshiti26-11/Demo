---
name: syncsnitch-workflow
description: SyncSnitch S0-S9 - detect an upstream contract change (REST, gRPC, DB), trace the consumer, generate a tolerant-reader adapter, verify it with mock containers, ask a human, then open a DRAFT companion PR.
---
# SyncSnitch workflow (S0-S9)

Inputs: `PR_URL` (e.g. https://github.com/kshiti26-11/orders-service/pull/1) and `CONSUMER` (default `../billing-service`).
Run every command from the main repo root `~/hack/syncsnitch`. Upstream = `../orders-service` (NEVER edit it).
Deterministic steps are shell commands: run them exactly, do not re-implement them. Keep messages short.
Artifacts live in `.syncsnitch/runs/<RUN_ID>/`.

## S0 - prepare (deterministic)
1. `gh pr view <PR_URL> --json number,headRefName,baseRefName` -> PR_NUMBER, HEAD_REF, BASE_REF.
2. `git -C ../orders-service fetch origin` and `git -C ../billing-service checkout main && git -C ../billing-service pull --ff-only`
3. `RUN_ID=r-$(date -u +%Y%m%d-%H%M%S)`; `mkdir -p .syncsnitch && touch .syncsnitch/ACTIVE` (turns the write-guard hook on).

## S1 - detect drift (deterministic, 0 tokens)
`uv run syncsnitch detect --upstream ../orders-service --base <BASE_REF> --head <HEAD_REF> --run-id <RUN_ID>`
Success: prints a change table and writes drift.json. If it reports 0 breaking changes: tell the user and stop.

## S2 - trace the consumer (deterministic)
`uv run syncsnitch trace --run-id <RUN_ID> --consumer <CONSUMER>`
Then copy the upstream change proposal for S3:
`git -C ../orders-service show "origin/<HEAD_REF>:docs/orders-v2-change-proposal.docx" > .syncsnitch/runs/<RUN_ID>/change-proposal.docx || true`

## S3 - Schema Diff & AST Tracer (AI)
Delegate to a sub-agent / mode `syncsnitch-tracer` with this task:
"Read .syncsnitch/runs/<RUN_ID>/drift.json and candidates.json, the consumer files they point to, and the change proposal
.syncsnitch/runs/<RUN_ID>/change-proposal.docx. Write .syncsnitch/runs/<RUN_ID>/impact.json exactly in this shape:
{"run_id": "...", "mapping": [{"change_ids": [...], "old": "total_price", "new": "total.amount_minor", "rule": "..."}],
 "affected": [{"file": "...", "line": 1, "symbol": "...", "change_ids": [...], "surface": "rest|grpc|db|test",
 "failure": "loud|silent|none", "endpoint": "POST /invoices/{order_id}" or null, "fix": "..."}],
 "endpoints": [{"endpoint": "...", "surface": "...", "failure": "loud|silent", "why": "..."}],
 "migration_notes": "3-6 sentences that quote the proposal's rollout and migration guidance"}
Reply with a 5-line summary."

## S4 - Downstream Code Transformer (AI)
Delegate to a sub-agent / mode `syncsnitch-transformer` with this task:
"In <CONSUMER>: `git checkout -b syncsnitch/orders-service-pr<PR_NUMBER> main`. Read .syncsnitch/runs/<RUN_ID>/impact.json and
apply .bob/rules-syncsnitch-transformer/tolerant-reader.md exactly (PR_NUMBER=<PR_NUMBER>, RUN_ID=<RUN_ID>).
Unit tests must pass. Commit on the branch. Do not push. Reply with the diffstat."

## S5 - verify with mock containers (deterministic; Docker must be running; 2-6 minutes)
`uv run syncsnitch verify --run-id <RUN_ID> --upstream ../orders-service --base <BASE_REF> --head <HEAD_REF> --consumer <CONSUMER>`
Writes verification.json and VERIFICATION.md (checks V1-V6: unit tests, v2 fixtures, containers vs v1, containers vs v2,
Prism contract examples, diff scope).

## S6 - Contract Verifier (AI)
Delegate to a sub-agent / mode `syncsnitch-verifier` with this task:
"Read .syncsnitch/runs/<RUN_ID>/verification.json. Write .syncsnitch/runs/<RUN_ID>/verdict.json:
{"run_id": "...", "verdict": "green|red", "reasons": [...], "fix_instructions": [...]}. Never edit code.
Deterministic checks are the only truth."
If red on the first round: give fix_instructions to the Transformer (S4 on the same branch), then S5 and S6 again.
If still red: stop, show VERIFICATION.md to the user, and ask what to do.

## S7 - human approval gate (interactive, never skip)
Show VERIFICATION.md and `git -C <CONSUMER> diff --stat main...HEAD`, then ask the user with these choices:
"Approve & open draft PR" / "Show full diff" / "Request changes" / "Abort".
- Show full diff -> `git -C <CONSUMER> diff main...HEAD`, then ask again.
- Request changes -> pass the user's words to the Transformer (S4), then S5-S7.
- Abort -> `rm -f .syncsnitch/ACTIVE` and stop.

## S8 - open the DRAFT companion PR (deterministic)
1. `uv run syncsnitch report --run-id <RUN_ID> --format pr --upstream-pr-url <PR_URL>` (writes pr_body.md)
2. `bash scripts/open_companion_pr.sh <CONSUMER> syncsnitch/orders-service-pr<PR_NUMBER> "SyncSnitch: adapt billing to Orders API v2 (orders-service#<PR_NUMBER>)" .syncsnitch/runs/<RUN_ID>/pr_body.md kshiti26-11/orders-service <PR_NUMBER>`
3. Read COMPANION_PR_URL from the last output line.
(Optional: if the user enabled the GitHub MCP server, you may create the draft PR and the upstream comment with it instead.)

## S9 - run artifact and wrap-up (deterministic)
1. `uv run syncsnitch run-artifact --run-id <RUN_ID> --consumer <CONSUMER> --branch syncsnitch/orders-service-pr<PR_NUMBER> --upstream-pr-url <PR_URL> --companion-pr-url <COMPANION_PR_URL>`
2. `rm -f .syncsnitch/ACTIVE`
3. Tell the user: companion PR URL, verification summary, the file web/runs/<RUN_ID>.json, and
   "Export this task now to bob_sessions/exports/P3-3-hero-run.md".
