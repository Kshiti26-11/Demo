#!/usr/bin/env bash
# Vendor pinned snapshots of the demo code into web/_vendor for the Vercel demo site.
# Deterministic (0 Bobcoins). Run from anywhere inside the main repo; expects the sibling
# checkouts ../orders-service and ../billing-service (see WORK.md setup).
# Usage: scripts/vendor_demo_code.sh <orders_v1_ref> <orders_v2_ref> <billing_before_ref> <billing_after_ref>
# Example: scripts/vendor_demo_code.sh main feat/orders-v2 main syncsnitch/orders-service-pr1
set -euo pipefail
if [ "$#" -ne 4 ]; then
  echo "usage: $0 <orders_v1_ref> <orders_v2_ref> <billing_before_ref> <billing_after_ref>" >&2
  exit 2
fi
root="$(git rev-parse --show-toplevel)"
orders="$root/../orders-service"
billing="$root/../billing-service"
vendor="$root/web/_vendor"

resolve() { # <repo> <ref> -> commit sha (tries <ref>, then origin/<ref>)
  git -C "$1" rev-parse --verify --quiet "$2^{commit}" || git -C "$1" rev-parse --verify "origin/$2^{commit}"
}
snap() { # <repo> <ref> <package_dir> <dest_name>; prints the pinned sha
  local sha
  sha="$(resolve "$1" "$2")"
  mkdir -p "$vendor/$4"
  git -C "$1" archive "$sha" "$3" | tar -x -C "$vendor/$4"
  echo "$sha"
}

git -C "$orders" fetch --quiet origin 2>/dev/null || true
git -C "$billing" fetch --quiet origin 2>/dev/null || true
rm -rf "$vendor"
mkdir -p "$vendor"
orders_v1="$(snap "$orders" "$1" orders_service orders_v1)"
orders_v2="$(snap "$orders" "$2" orders_service orders_v2)"
billing_before="$(snap "$billing" "$3" billing billing_before)"
billing_after="$(snap "$billing" "$4" billing billing_after)"
engine="$(git -C "$root" rev-parse HEAD)"
mkdir -p "$vendor/syncsnitch_engine"
git -C "$root" archive HEAD syncsnitch | tar -x -C "$vendor/syncsnitch_engine"
find "$vendor" -name "__pycache__" -type d -prune -exec rm -rf {} +
cat > "$vendor/PINS.json" <<JSON
{
  "orders_v1": {"ref": "$1", "sha": "$orders_v1"},
  "orders_v2": {"ref": "$2", "sha": "$orders_v2"},
  "billing_before": {"ref": "$3", "sha": "$billing_before"},
  "billing_after": {"ref": "$4", "sha": "$billing_after"},
  "syncsnitch_engine": {"ref": "HEAD", "sha": "$engine"}
}
JSON
echo "vendored into $vendor:"
cat "$vendor/PINS.json"
