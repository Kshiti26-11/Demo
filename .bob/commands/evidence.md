---
description: Show the bob_sessions evidence checklist for the task you just finished
---
Print this checklist and nothing else:
1. Bob History -> Export this task -> save as ~/hack/syncsnitch/bob_sessions/exports/P<person>-<step>-<slug>.md
2. Save 1-3 screenshots -> ~/hack/syncsnitch/bob_sessions/screenshots/P<person>-<step>-<n>-<what>.png
3. cd ~/hack/syncsnitch && git add bob_sessions/exports/P<person>-<step>-* bob_sessions/screenshots/P<person>-<step>-*
   && git commit -m "evidence: P<person>-<step>" && git pull --rebase origin main && git push origin main
