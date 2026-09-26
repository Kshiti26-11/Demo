"""Tests for detect: REST, gRPC, and DB drift detection using reference contracts."""
from __future__ import annotations

from pathlib import Path

import pytest

# Paths to reference contracts
_REFS = Path(__file__).parent.parent.parent / "contracts" / "reference"
_V1_OPENAPI = _REFS / "v1" / "openapi.yaml"
_V2_OPENAPI = _REFS / "v2" / "openapi.yaml"
_V1_PROTO = _REFS / "v1" / "orders.proto"
_V2_PROTO = _REFS / "v2" / "orders.proto"
_MIG_0001 = _REFS / "migrations" / "0001_create_orders.py"
_MIG_0002 = _REFS / "migrations" / "0002_money_customer_status.py"


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------

class TestRestDrift:
    def test_exactly_3_breaking_changes(self):
        from syncsnitch.detect.openapi import diff_openapi

        old = _V1_OPENAPI.read_text(encoding="utf-8")
        new = _V2_OPENAPI.read_text(encoding="utf-8")
        changes = diff_openapi(old, new)
        breaking = [c for c in changes if c["breaking"]]
        assert len(breaking) == 3, (
            f"Expected 3 breaking REST changes, got {len(breaking)}: "
            + str([c["id"] for c in breaking])
        )

    def test_customer_name_removed(self):
        from syncsnitch.detect.openapi import diff_openapi

        old = _V1_OPENAPI.read_text(encoding="utf-8")
        new = _V2_OPENAPI.read_text(encoding="utf-8")
        changes = diff_openapi(old, new)
        ids = {c["id"] for c in changes}
        assert "rest:Order.customer_name:property_removed" in ids

    def test_total_price_removed(self):
        from syncsnitch.detect.openapi import diff_openapi

        old = _V1_OPENAPI.read_text(encoding="utf-8")
        new = _V2_OPENAPI.read_text(encoding="utf-8")
        changes = diff_openapi(old, new)
        ids = {c["id"] for c in changes}
        assert "rest:Order.total_price:property_removed" in ids

    def test_pending_enum_removed(self):
        from syncsnitch.detect.openapi import diff_openapi

        old = _V1_OPENAPI.read_text(encoding="utf-8")
        new = _V2_OPENAPI.read_text(encoding="utf-8")
        changes = diff_openapi(old, new)
        ids = {c["id"] for c in changes}
        assert "rest:OrderStatus.PENDING:enum_value_removed" in ids

    def test_change_shape(self):
        from syncsnitch.detect.openapi import diff_openapi

        old = _V1_OPENAPI.read_text(encoding="utf-8")
        new = _V2_OPENAPI.read_text(encoding="utf-8")
        changes = diff_openapi(old, new)
        required_keys = {"id", "surface", "kind", "location", "old", "new", "breaking", "note"}
        for c in changes:
            assert required_keys <= set(c.keys()), f"Missing keys in {c}"
            assert c["surface"] == "rest"
            assert c["id"] == f"rest:{c['location']}:{c['kind']}"


# ---------------------------------------------------------------------------
# gRPC
# ---------------------------------------------------------------------------

class TestGrpcDrift:
    def test_exactly_3_breaking_changes(self):
        from syncsnitch.detect.proto import diff_proto_texts

        old = _V1_PROTO.read_text(encoding="utf-8")
        new = _V2_PROTO.read_text(encoding="utf-8")
        changes = diff_proto_texts(old, new)
        breaking = [c for c in changes if c["breaking"]]
        assert len(breaking) == 3, (
            f"Expected 3 breaking gRPC changes, got {len(breaking)}: "
            + str([c["id"] for c in breaking])
        )

    def test_customer_name_field_removed(self):
        from syncsnitch.detect.proto import diff_proto_texts

        old = _V1_PROTO.read_text(encoding="utf-8")
        new = _V2_PROTO.read_text(encoding="utf-8")
        changes = diff_proto_texts(old, new)
        kinds = {c["kind"] for c in changes if c["breaking"]}
        # customer_name and total_price removed; enum renamed
        removed = [c for c in changes if c["kind"] == "field_removed" and c["breaking"]]
        assert len(removed) == 2, f"Expected 2 field_removed, got {removed}"

    def test_enum_rename_breaking(self):
        from syncsnitch.detect.proto import diff_proto_texts

        old = _V1_PROTO.read_text(encoding="utf-8")
        new = _V2_PROTO.read_text(encoding="utf-8")
        changes = diff_proto_texts(old, new)
        renames = [c for c in changes if c["kind"] == "enum_value_renamed" and c["breaking"]]
        assert any(c["old"] == "ORDER_STATUS_PENDING" for c in renames), \
            f"Expected ORDER_STATUS_PENDING rename: {renames}"

    def test_change_shape(self):
        from syncsnitch.detect.proto import diff_proto_texts

        old = _V1_PROTO.read_text(encoding="utf-8")
        new = _V2_PROTO.read_text(encoding="utf-8")
        changes = diff_proto_texts(old, new)
        required_keys = {"id", "surface", "kind", "location", "old", "new", "breaking", "note"}
        for c in changes:
            assert required_keys <= set(c.keys()), f"Missing keys in {c}"


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

class TestDbDrift:
    def test_exactly_3_breaking_changes(self):
        from syncsnitch.detect.migrations import diff_migrations

        mig = _MIG_0002.read_text(encoding="utf-8")
        changes = diff_migrations([mig])
        breaking = [c for c in changes if c["breaking"]]
        assert len(breaking) == 3, (
            f"Expected 3 breaking DB changes, got {len(breaking)}: "
            + str([c["id"] for c in breaking])
        )

    def test_column_renamed(self):
        from syncsnitch.detect.migrations import diff_migrations

        mig = _MIG_0002.read_text(encoding="utf-8")
        changes = diff_migrations([mig])
        renames = [c for c in changes if c["kind"] == "column_renamed" and c["breaking"]]
        assert any(c["old"] == "customer_name" for c in renames), \
            f"Expected customer_name rename: {renames}"

    def test_column_dropped(self):
        from syncsnitch.detect.migrations import diff_migrations

        mig = _MIG_0002.read_text(encoding="utf-8")
        changes = diff_migrations([mig])
        drops = [c for c in changes if c["kind"] == "column_dropped" and c["breaking"]]
        assert any(c["old"] == "total_price" for c in drops), \
            f"Expected total_price drop: {drops}"

    def test_value_renamed(self):
        from syncsnitch.detect.migrations import diff_migrations

        mig = _MIG_0002.read_text(encoding="utf-8")
        changes = diff_migrations([mig])
        renames = [c for c in changes if c["kind"] == "value_renamed" and c["breaking"]]
        assert any(c["old"] == "PENDING" and c["new"] == "AWAITING_PAYMENT" for c in renames), \
            f"Expected PENDING->AWAITING_PAYMENT value rename: {renames}"

    def test_change_shape(self):
        from syncsnitch.detect.migrations import diff_migrations

        mig = _MIG_0002.read_text(encoding="utf-8")
        changes = diff_migrations([mig])
        required_keys = {"id", "surface", "kind", "location", "old", "new", "breaking", "note"}
        for c in changes:
            assert required_keys <= set(c.keys()), f"Missing keys in {c}"


# ---------------------------------------------------------------------------
# Combined: 9 breaking changes total
# ---------------------------------------------------------------------------

class TestCombinedBreakingCount:
    def test_9_breaking_changes_total(self):
        from syncsnitch.detect.openapi import diff_openapi
        from syncsnitch.detect.proto import diff_proto_texts
        from syncsnitch.detect.migrations import diff_migrations

        rest_changes = diff_openapi(
            _V1_OPENAPI.read_text(encoding="utf-8"),
            _V2_OPENAPI.read_text(encoding="utf-8"),
        )
        grpc_changes = diff_proto_texts(
            _V1_PROTO.read_text(encoding="utf-8"),
            _V2_PROTO.read_text(encoding="utf-8"),
        )
        db_changes = diff_migrations([_MIG_0002.read_text(encoding="utf-8")])

        all_changes = rest_changes + grpc_changes + db_changes
        breaking = [c for c in all_changes if c["breaking"]]
        assert len(breaking) == 9, (
            f"Expected 9 total breaking changes, got {len(breaking)}: "
            + str([c["id"] for c in breaking])
        )
