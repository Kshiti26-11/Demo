from pathlib import Path
import tempfile
from typing import Any
from google.protobuf import descriptor_pb2


def compile_proto(text: str) -> bytes:
    import grpc_tools
    from grpc_tools import protoc

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        proto_path = tmp_path / "orders.proto"
        proto_path.write_text(text, encoding="utf-8")
        out_binpb = tmp_path / "out.binpb"
        proto_include = Path(grpc_tools.__file__).parent / "_proto"

        args = [
            "grpc_tools.protoc",
            f"-I{tmp_path}",
            f"-I{proto_include}",
            "--include_imports",
            f"--descriptor_set_out={out_binpb}",
            str(proto_path),
        ]
        rc = protoc.main(args)
        if rc != 0 or not out_binpb.exists():
            raise RuntimeError(f"protoc failed with exit code {rc}")
        return out_binpb.read_bytes()


def diff_descriptor_sets(old: bytes, new: bytes) -> list[dict[str, Any]]:
    old_fds = descriptor_pb2.FileDescriptorSet.FromString(old)
    new_fds = descriptor_pb2.FileDescriptorSet.FromString(new)

    # Map full names to descriptors for primary files (usually the last or non-standard ones)
    def collect_definitions(fds: descriptor_pb2.FileDescriptorSet):
        messages = {}
        enums = {}
        for f in fds.file:
            # Skip standard google/protobuf files if any
            if f.name.startswith("google/protobuf/"):
                continue
            pkg = f.package
            prefix = f"{pkg}." if pkg else ""
            for m in f.message_type:
                messages[f"{prefix}{m.name}"] = (pkg, m)
            for e in f.enum_type:
                enums[f"{prefix}{e.name}"] = (pkg, e)
        return messages, enums

    old_messages, old_enums = collect_definitions(old_fds)
    new_messages, new_enums = collect_definitions(new_fds)

    changes: list[dict[str, Any]] = []

    def make_change(kind: str, location: str, old_val: Any = None, new_val: Any = None, breaking: bool = False, note: str = "") -> dict[str, Any]:
        return {
            "id": f"grpc:{location}:{kind}",
            "surface": "grpc",
            "kind": kind,
            "location": location,
            "old": old_val,
            "new": new_val,
            "breaking": breaking,
            "note": note,
        }

    # Messages added / removed
    for mname in sorted(new_messages.keys()):
        if mname not in old_messages:
            changes.append(make_change("message_added", mname, new_val=mname, breaking=False))

    for mname in sorted(old_messages.keys()):
        if mname not in new_messages:
            changes.append(make_change("message_removed", mname, old_val=mname, breaking=True))

    # Compare common messages by field numbers
    for mname in sorted(set(old_messages.keys()) & set(new_messages.keys())):
        pkg, old_m = old_messages[mname]
        _, new_m = new_messages[mname]

        old_fields = {f.number: f for f in old_m.field}
        new_fields = {f.number: f for f in new_m.field}

        all_numbers = sorted(set(old_fields.keys()) | set(new_fields.keys()))
        for num in all_numbers:
            loc = f"{mname}.{num}"
            if num in old_fields and num not in new_fields:
                changes.append(make_change("field_removed", loc, old_val=old_fields[num].name, breaking=True))
            elif num in new_fields and num not in old_fields:
                changes.append(make_change("field_added", loc, new_val=new_fields[num].name, breaking=False))
            else:
                of = old_fields[num]
                nf = new_fields[num]
                if of.name != nf.name:
                    changes.append(make_change("field_renamed", loc, old_val=of.name, new_val=nf.name, breaking=True))
                elif of.type != nf.type or of.type_name != nf.type_name:
                    changes.append(make_change("field_type_changed", loc, old_val=of.type_name or str(of.type), new_val=nf.type_name or str(nf.type), breaking=True))

    # Compare enums by value numbers
    for ename in sorted(new_enums.keys()):
        if ename not in old_enums:
            changes.append(make_change("enum_added", ename, new_val=ename, breaking=False))

    for ename in sorted(old_enums.keys()):
        if ename not in new_enums:
            changes.append(make_change("enum_removed", ename, old_val=ename, breaking=True))

    for ename in sorted(set(old_enums.keys()) & set(new_enums.keys())):
        pkg, old_e = old_enums[ename]
        _, new_e = new_enums[ename]

        old_vals = {v.number: v for v in old_e.value}
        new_vals = {v.number: v for v in new_e.value}

        for num in sorted(set(old_vals.keys()) | set(new_vals.keys())):
            loc = f"{ename}.{num}"
            if num in old_vals and num not in new_vals:
                changes.append(make_change("enum_value_removed", loc, old_val=old_vals[num].name, breaking=True))
            elif num in new_vals and num not in old_vals:
                changes.append(make_change("enum_value_added", loc, new_val=new_vals[num].name, breaking=False))
            else:
                ov = old_vals[num]
                nv = new_vals[num]
                if ov.name != nv.name:
                    changes.append(make_change(
                        "enum_value_renamed",
                        loc,
                        old_val=ov.name,
                        new_val=nv.name,
                        breaking=True,
                        note="wire-compatible, source-breaking",
                    ))

    return changes


def diff_proto_texts(old_text: str, new_text: str) -> list[dict[str, Any]]:
    return diff_descriptor_sets(compile_proto(old_text), compile_proto(new_text))
