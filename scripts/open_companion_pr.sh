#!/usr/bin/env bash
# Push the SyncSnitch branch and open a DRAFT companion PR in the consumer repo,
# then link it from the upstream PR. Deterministic (0 Bobcoins).
# Usage: scripts/open_companion_pr.sh <consumer_dir> <branch> <title> <body_file> <upstream_repo> <upstream_pr_number> [base_branch]
#   upstream_pr_number "-" = there is no upstream PR to comment on (link mode from the website)
#   base_branch defaults to main (link mode: the branch the fix was made from, e.g. branch1 in a monorepo)
set -euo pipefail
if [ "$#" -ne 6 ] && [ "$#" -ne 7 ]; then
  echo "usage: $0 <consumer_dir> <branch> <title> <body_file> <upstream_repo> <upstream_pr_number|-> [base_branch]" >&2
  exit 2
fi
consumer_dir=$1
branch=$2
title=$3
body_file=$4
upstream_repo=$5
upstream_pr=$6
base_branch=${7:-main}
command -v gh >/dev/null || { echo "gh CLI not found: install it and run 'gh auth login'" >&2; exit 3; }
body_abs="$(cd "$(dirname "$body_file")" && pwd)/$(basename "$body_file")"
cd "$consumer_dir"
git push -u origin "$branch"
url=$(gh pr create --draft --base "$base_branch" --head "$branch" --title "$title" --body-file "$body_abs")
if [ "$upstream_pr" != "-" ]; then
  gh pr comment "$upstream_pr" --repo "$upstream_repo" \
    --body "SyncSnitch opened a verified DRAFT companion PR for this contract change: $url"
fi
echo "COMPANION_PR_URL=$url"
