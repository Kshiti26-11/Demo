"""gRPC/protobuf drift detection."""
from __future__ import annotations

import os
import tempfile
from typing import Any


def compile_proto(text: str) -> bytes:
    """Compile proto text to a descriptor set bytes. Lazy-imports grpc_tools."""
    from grpc_tools import protoc  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmpdir:
        proto_path = os.path.join(tmpdir, "orders.proto")
        desc_path = os.path.join(tmpdir, "descriptor.pb")
        with open(proto_path, "w", encoding="utf-8") as fh:
            fh.write(text)

        # grpc_tools bundles its own well-known includes
        import grpc_tools
        grpc_include = os.path.join(os.path.dirname(grpc_tools.__file__), "_proto")

        args = [
            "grpc_tools.protoc",
            f"-I{tmpdir}",
            f"-I{grpc_include}",
            f"--descriptor_set_out={desc_path}",
            "--include_imports",
            proto_path,
        ]
        rc = protoc.main(args)
        if rc != 0:
            raise RuntimeError(f"protoc failed with code {rc}")
        with open(desc_path, "rb") as fh:
            return fh.read()


def _parse_descriptor(data: bytes) -> Any:
    """Parse descriptor bytes without registering in the global pool."""
    from google.protobuf import descriptor_pb2  # noqa: PLC0415

    fds = descriptor_pb2.FileDescriptorSet()
    fds.ParseFromString(data)
    return fds


def diff_descriptor_sets(old_data: bytes, new_data: bytes) -> list[dict]:
    """Compare two serialised FileDescriptorSet blobs and return Change dicts."""
    from google.protobuf import descriptor_pb2  # noqa: PLC0415

    old_fds = _parse_descriptor(old_data)
    new_fds = _parse_descriptor(new_data)

    # index messages and enums by qualified name
    def _index(fds: descriptor_pb2.FileDescriptorSet):
        messages: dict[str, descriptor_pb2.DescriptorProto] = {}
        enums: dict[str, descriptor_pb2.EnumDescriptorProto] = {}
        for f in fds.file:
            pkg = f.package
            prefix = f"{pkg}." if pkg else ""
            for msg in f.message_type:
                messages[f"{prefix}{msg.name}"] = msg
            for en in f.enum_type:
                enums[f"{prefix}{en.name}"] = en
        return messages, enums

    old_msgs, old_enums = _index(old_fds)
    new_msgs, new_enums = _index(new_fds)

    changes: list[dict] = []

    # message_added / message_removed
    for qname in new_msgs:
        if qname not in old_msgs:
            changes.append(_mk("grpc", qname, "message_added", qname, None, qname, False, ""))
    for qname in old_msgs:
        if qname not in new_msgs:
            changes.append(_mk("grpc", qname, "message_removed", qname, qname, None, True, ""))

    # per-message field comparison
    for qname in old_msgs:
        if qname not in new_msgs:
            continue
        old_fields = {f.number: f for f in old_msgs[qname].field}
        new_fields = {f.number: f for f in new_msgs[qname].field}

        for num, fld in old_fields.items():
            loc = f"{qname}.{fld.name}"
            if num not in new_fields:
                changes.append(_mk("grpc", loc, "field_removed", loc, fld.name, None, True, ""))
            else:
                nfld = new_fields[num]
                if nfld.name != fld.name:
                    changes.append(_mk("grpc", loc, "field_renamed", loc, fld.name, nfld.name,
                                       True, "wire-compatible, source-breaking"))
                elif nfld.type != fld.type:
                    changes.append(_mk("grpc", f"{qname}.{fld.name}", "field_type_changed",
                                       f"{qname}.{fld.name}", fld.type, nfld.type, True, ""))

        for num, fld in new_fields.items():
            if num not in old_fields:
                loc = f"{qname}.{fld.name}"
                changes.append(_mk("grpc", loc, "field_added", loc, None, fld.name, False, ""))

    # enum comparison
    for qname in new_enums:
        if qname not in old_enums:
            changes.append(_mk("grpc", qname, "message_added", qname, None, qname, False, ""))
    for qname in old_enums:
        if qname not in new_enums:
            changes.append(_mk("grpc", qname, "message_removed", qname, qname, None, True, ""))

    for qname in old_enums:
        if qname not in new_enums:
            continue
        old_vals = {v.number: v for v in old_enums[qname].value}
        new_vals = {v.number: v for v in new_enums[qname].value}

        for num, val in old_vals.items():
            loc = f"{qname}.{val.name}"
            if num not in new_vals:
                changes.append(_mk("grpc", loc, "enum_value_removed", loc,
                                   val.name, None, True, ""))
            else:
                nval = new_vals[num]
                if nval.name != val.name:
                    changes.append(_mk("grpc", loc, "enum_value_renamed", loc,
                                       val.name, nval.name, True,
                                       "wire-compatible, source-breaking"))

        for num, val in new_vals.items():
            if num not in old_vals:
                loc = f"{qname}.{val.name}"
                changes.append(_mk("grpc", loc, "enum_value_added", loc,
                                   None, val.name, False, ""))

    return changes


def _mk(surface, location, kind, loc, old, new, breaking, note) -> dict:
    return {
        "id": f"{surface}:{loc}:{kind}",
        "surface": surface,
        "kind": kind,
        "location": location,
        "old": old,
        "new": new,
        "breaking": breaking,
        "note": note,
    }


def diff_proto_texts(old_text: str, new_text: str) -> list[dict]:
    """Compile both proto texts and diff the resulting descriptor sets."""
    old_data = compile_proto(old_text)
    new_data = compile_proto(new_text)
    return diff_descriptor_sets(old_data, new_data)
