#!/usr/bin/env bash
# Vendor pinned snapshots of the demo code into web/_vendor for the Vercel demo site.
# Deterministic (0 Bobcoins). Run from anywhere inside the main repo. Works with either layout:
#   - sibling checkouts ../orders-service and ../billing-service (WORK.md setup), or
#   - a monorepo with orders-service/ and billing-service/ inside this repo (kshiti26-11/demo).
# A ref of "." copies the current working tree (uncommitted changes included) instead of a commit;
# the engine is always copied from the working tree.
# Usage: scripts/vendor_demo_code.sh <orders_v1_ref> <orders_v2_ref> <billing_before_ref> <billing_after_ref>
# Example: scripts/vendor_demo_code.sh main feat/orders-v2 main syncsnitch/orders-service-pr1
set -euo pipefail
if [ "$#" -ne 4 ]; then
  echo "usage: $0 <orders_v1_ref> <orders_v2_ref> <billing_before_ref> <billing_after_ref>" >&2
  exit 2
fi
root="$(git rev-parse --show-toplevel)"
if [ -d "$root/../orders-service/.git" ] && [ -d "$root/../billing-service/.git" ]; then
  orders="$root/../orders-service"; orders_sub=""
  billing="$root/../billing-service"; billing_sub=""
else
  orders="$root"; orders_sub="orders-service/"
  billing="$root"; billing_sub="billing-service/"
fi
vendor="$root/web/_vendor"

resolve() { # <repo> <ref> -> commit sha (tries <ref>, then origin/<ref>)
  git -C "$1" rev-parse --verify --quiet "$2^{commit}" || git -C "$1" rev-parse --verify "origin/$2^{commit}"
}
snap() { # <repo> <sub-folder/> <ref> <package_dir> <dest_name>; prints the pinned sha
  local sha strip
  mkdir -p "$vendor/$5"
  if [ "$3" = "." ]; then
    cp -R "$1/$2$4" "$vendor/$5/"
    echo "working-tree@$(git -C "$1" rev-parse --short HEAD)"
    return
  fi
  sha="$(resolve "$1" "$3")"
  strip=0; [ -n "$2" ] && strip=1
  git -C "$1" archive "$sha" "$2$4" | tar -x -C "$vendor/$5" --strip-components="$strip"
  echo "$sha"
}

git -C "$orders" fetch --quiet origin 2>/dev/null || true
git -C "$billing" fetch --quiet origin 2>/dev/null || true
rm -rf "$vendor"
mkdir -p "$vendor"
orders_v1="$(snap "$orders" "$orders_sub" "$1" orders_service orders_v1)"
orders_v2="$(snap "$orders" "$orders_sub" "$2" orders_service orders_v2)"
billing_before="$(snap "$billing" "$billing_sub" "$3" billing billing_before)"
billing_after="$(snap "$billing" "$billing_sub" "$4" billing billing_after)"
engine="$(snap "$root" "" . syncsnitch syncsnitch_engine)"
find "$vendor" -name "__pycache__" -type d -prune -exec rm -rf {} +
cat > "$vendor/PINS.json" <<JSON
{
  "orders_v1": {"ref": "$1", "sha": "$orders_v1"},
  "orders_v2": {"ref": "$2", "sha": "$orders_v2"},
  "billing_before": {"ref": "$3", "sha": "$billing_before"},
  "billing_after": {"ref": "$4", "sha": "$billing_after"},
  "syncsnitch_engine": {"ref": "working tree", "sha": "$engine"}
}
JSON
echo "vendored into $vendor:"
cat "$vendor/PINS.json"
