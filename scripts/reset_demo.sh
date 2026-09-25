#!/usr/bin/env bash
# Reset the demo so /syncsnitch can run again: close open SyncSnitch companion PRs (and delete
# their remote branches), delete local syncsnitch/* branches in billing-service, clear .syncsnitch/.
# Recorded runs in web/runs/ are kept. Default is a dry run; pass --apply to execute.
# Usage: scripts/reset_demo.sh [--apply]
set -euo pipefail
apply="${1:-}"
root="$(git rev-parse --show-toplevel)"
billing_dir="$root/../billing-service"
billing_repo="kshiti26-11/billing-service"

run() {
  if [ "$apply" = "--apply" ]; then
    echo "+ $*"
    "$@"
  else
    echo "(dry run) $*"
  fi
}

for n in $(gh pr list --repo "$billing_repo" --state open --json number,headRefName \
  --jq '.[] | select(.headRefName | startswith("syncsnitch/")) | .number'); do
  run gh pr close "$n" --repo "$billing_repo" --delete-branch --comment "Closed by scripts/reset_demo.sh (demo reset)"
done
run git -C "$billing_dir" checkout main
for b in $(git -C "$billing_dir" branch --list 'syncsnitch/*' --format '%(refname:short)'); do
  run git -C "$billing_dir" branch -D "$b"
done
run rm -rf "$root/.syncsnitch"
[ "$apply" = "--apply" ] || echo "Dry run only. Re-run with --apply to execute."
