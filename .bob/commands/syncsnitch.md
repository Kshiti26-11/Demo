---
description: Run the SyncSnitch contract-drift workflow (auto-runs S0-S7)
argument-hint: [upstream-pr-url | syncsnitch-site-analyze-link] [consumer-path]
---
Switch to the "SyncSnitch" mode (slug: syncsnitch) and run the skill .bob/skills/syncsnitch-workflow/SKILL.md from S0 to S9.
If no argument is given, run Auto mode (auto-detect upstream orders-service and consumer billing-service, run S0 through S6 with the 3 subagents, and stop at S7 for human approval).
If $1 contains "/analyze?", run Link mode with LINK=$1.
If $1 is a PR URL or branch, run PR mode with PR_URL=$1 and CONSUMER=$2.
Do NOT stop to ask questions before S7. Run automatically through S0, S1, S2, delegate S3 to the Tracer subagent, delegate S4 to the Transformer subagent, run S5 verify, and delegate S6 to the Verifier subagent.
Stop at S7 and wait for my decision. Keep every message short.
