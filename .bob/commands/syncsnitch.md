---
description: Run the SyncSnitch contract-drift workflow for an upstream PR
argument-hint: <upstream-pr-url> [consumer-path]
---
Switch to the "SyncSnitch" mode (slug: syncsnitch) and run the skill .bob/skills/syncsnitch-workflow/SKILL.md
from S0 to S9 with PR_URL=$1 and CONSUMER=$2 (use ../billing-service when $2 is empty).
Stop at S7 and wait for my decision. Keep every message short.
