# SyncSnitch guardrails (apply in every mode)
- Never merge a pull request. Companion PRs are always DRAFT.
- Never edit the upstream repository (../orders-service) during a SyncSnitch run.
- Deterministic commands decide pass/fail; a model never overrides a failing check.
- Stop at the human approval gate (S7) and wait.
- Never print or commit secrets (.env files, tokens).
- Save Bobcoins: do not explore or search broadly, read only the files named in the task, write several files per turn,
  never echo file contents back, keep replies short.
- Commits made in a Bob task carry the trailer "Bob-Session: <prompt id>".
