# bob_sessions — IBM Bob evidence (hackathon requirement)

Every Bob task we run is exported here. Judges use this folder to see that IBM Bob built SyncSnitch.

## Naming (unique per person, so nobody ever conflicts)
| What | Where | Name |
|---|---|---|
| Exported task history | `bob_sessions/exports/` | `P<person>-<step>-<slug>.md`, e.g. `P1-1-orders-v1.md` |
| Screenshots | `bob_sessions/screenshots/` | `P<person>-<step>-<n>-<what>.png`, e.g. `P3-3-2-approval-gate.png` |
| Hook logs (automatic) | `bob_sessions/raw/` | written by `scripts/bob_hooks/logger.py` |
| Bobalytics screenshots | `bob_sessions/screenshots/` | `bobalytics-<round>.png` |

## How to add your evidence (copy the snippet printed under each prompt in WORK.md)
1. In Bob: open **History**, then **Export** the task, and save it into `bob_sessions/exports/` with the name above.
2. Save 1–3 screenshots of the key moments into `bob_sessions/screenshots/`.
3. Commit only your own files, then `git pull --rebase origin main` and `git push origin main`.

## Index
Filled in at the end by Person 3 (WORK.md prompt P3-4 or by hand). Do not edit this section before then.

| Step | Person | What Bob built | Export | Screenshots |
|---|---|---|---|---|
