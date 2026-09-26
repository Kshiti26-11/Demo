"""gRPC/protobuf drift detection."""
from __future__ import annotations

import os
import re
import tempfile


def compile_proto(text: str) -> bytes:
    """Compile proto text to a serialised FileDescriptorSet with grpc_tools (lazy import)."""
    import grpc_tools  # noqa: PLC0415
    from grpc_tools import protoc  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmpdir:
        proto_path = os.path.join(tmpdir, "orders.proto")
        desc_path = os.path.join(tmpdir, "out.binpb")
        with open(proto_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        grpc_include = os.path.join(os.path.dirname(grpc_tools.__file__), "_proto")
        rc = protoc.main([
            "grpc_tools.protoc",
            f"-I{tmpdir}",
            f"-I{grpc_include}",
            "--include_imports",
            f"--descriptor_set_out={desc_path}",
            proto_path,
        ])
        if rc != 0:
            raise RuntimeError(f"protoc failed with code {rc}")
        with open(desc_path, "rb") as fh:
            return fh.read()


# ---------------------------------------------------------------------------
# Pure-Python fallback (the Vercel demo site ships without grpcio-tools on purpose)
# ---------------------------------------------------------------------------

_SCALARS = {
    "double": 1, "float": 2, "int64": 3, "uint64": 4, "int32": 5, "fixed64": 6, "fixed32": 7, "bool": 8,
    "string": 9, "bytes": 12, "uint32": 13, "sfixed32": 15, "sfixed64": 16, "sint32": 17, "sint64": 18,
}
_TYPE_MESSAGE, _TYPE_ENUM = 11, 14
_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[A-Za-z_][\w.]*|-?\d+|[{}\[\]=;<>,()]')


def parse_proto_text(text: str) -> bytes:
    """
    Parse a simple proto3 file (package, top-level and nested messages/enums, scalar and message/enum fields)
    into a serialised FileDescriptorSet. Field and enum numbers - what the diff compares - are exact; options
    and services are skipped. Used only when grpc_tools is not installed.
    """
    from google.protobuf import descriptor_pb2  # noqa: PLC0415

    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    tokens = _TOKEN.findall(text)
    pos = 0
    fdp = descriptor_pb2.FileDescriptorProto(name="orders.proto", syntax="proto3")
    fields_to_type: list[tuple[object, str]] = []
    enum_names: set[str] = set()

    def skip_block() -> None:
        nonlocal pos
        depth = 0
        while pos < len(tokens):
            tok = tokens[pos]
            pos += 1
            if tok == "{":
                depth += 1
            elif tok == "}":
                depth -= 1
                if depth == 0:
                    return

    def skip_statement() -> None:
        nonlocal pos
        while pos < len(tokens) and tokens[pos] != ";":
            pos += 1
        pos += 1

    def parse_enum(target, scope: str) -> None:
        nonlocal pos
        name = tokens[pos + 1]
        enum_names.add(f"{scope}{name}")
        en = target.add(name=name)
        pos += 3  # enum <name> {
        while tokens[pos] != "}":
            if tokens[pos] in ("option", "reserved"):
                skip_statement()
                continue
            en.value.add(name=tokens[pos], number=int(tokens[pos + 2]))
            skip_statement()
        pos += 1

    def parse_message(target, scope: str) -> None:
        nonlocal pos
        name = tokens[pos + 1]
        msg = target.add(name=name)
        inner = f"{scope}{name}."
        pos += 3  # message <name> {
        while tokens[pos] != "}":
            tok = tokens[pos]
            if tok == "message":
                parse_message(msg.nested_type, inner)
            elif tok == "enum":
                parse_enum(msg.enum_type, inner)
            elif tok in ("option", "reserved", "extensions"):
                skip_statement()
            elif tok in ("oneof", "map") or tokens[pos + 1] == "{":
                skip_block() if tok == "oneof" else skip_statement()
            else:
                label = 1
                if tok in ("optional", "repeated"):
                    label = 3 if tok == "repeated" else 1
                    pos += 1
                ftype, fname, number = tokens[pos], tokens[pos + 1], int(tokens[pos + 3])
                field = msg.field.add(name=fname, number=number, label=label)
                if ftype in _SCALARS:
                    field.type = _SCALARS[ftype]
                else:
                    fields_to_type.append((field, ftype))
                skip_statement()
        pos += 1

    while pos < len(tokens):
        tok = tokens[pos]
        if tok == "package":
            fdp.package = tokens[pos + 1]
            skip_statement()
        elif tok == "message":
            parse_message(fdp.message_type, "")
        elif tok == "enum":
            parse_enum(fdp.enum_type, "")
        elif tok == "service":
            skip_block()
        else:
            skip_statement()

    prefix = f".{fdp.package}." if fdp.package else "."
    for field, ftype in fields_to_type:
        name = ftype.lstrip(".")
        field.type = _TYPE_ENUM if name in enum_names or name.split(".")[-1] in enum_names else _TYPE_MESSAGE
        field.type_name = ftype if ftype.startswith(".") else prefix + name

    return descriptor_pb2.FileDescriptorSet(file=[fdp]).SerializeToString()


def to_descriptor_set(text: str) -> bytes:
    """compile_proto when grpc_tools is available, otherwise the pure-Python parser."""
    try:
        import grpc_tools  # noqa: F401, PLC0415
    except ImportError:
        return parse_proto_text(text)
    return compile_proto(text)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def _mk(location: str, kind: str, old, new, breaking: bool, note: str = "") -> dict:
    return {
        "id": f"grpc:{location}:{kind}",
        "surface": "grpc",
        "kind": kind,
        "location": location,
        "old": old,
        "new": new,
        "breaking": breaking,
        "note": note,
    }


def _index(fds) -> tuple[dict, dict]:
    """Messages and enums by "<package>.<Name>" (nested ones as "<package>.<Outer>.<Name>")."""
    messages: dict = {}
    enums: dict = {}

    def walk(prefix: str, msgs, ens) -> None:
        for en in ens:
            enums[f"{prefix}{en.name}"] = en
        for msg in msgs:
            messages[f"{prefix}{msg.name}"] = msg
            walk(f"{prefix}{msg.name}.", msg.nested_type, msg.enum_type)

    for f in fds.file:
        walk(f"{f.package}." if f.package else "", f.message_type, f.enum_type)
    return messages, enums


def diff_descriptor_sets(old: bytes, new: bytes) -> list[dict]:
    """Compare two serialised FileDescriptorSets (never added to a descriptor pool)."""
    from google.protobuf import descriptor_pb2  # noqa: PLC0415

    old_msgs, old_enums = _index(descriptor_pb2.FileDescriptorSet.FromString(old))
    new_msgs, new_enums = _index(descriptor_pb2.FileDescriptorSet.FromString(new))
    changes: list[dict] = []

    for qname in new_msgs.keys() - old_msgs.keys():
        changes.append(_mk(qname, "message_added", None, qname, False))
    for qname in old_msgs.keys() - new_msgs.keys():
        changes.append(_mk(qname, "message_removed", qname, None, True))

    for qname in old_msgs.keys() & new_msgs.keys():
        old_fields = {f.number: f for f in old_msgs[qname].field}
        new_fields = {f.number: f for f in new_msgs[qname].field}
        for num, fld in old_fields.items():
            loc = f"{qname}.{num}"
            if num not in new_fields:
                changes.append(_mk(loc, "field_removed", fld.name, None, True))
                continue
            nfld = new_fields[num]
            if nfld.name != fld.name:
                changes.append(_mk(loc, "field_renamed", fld.name, nfld.name, True))
            if (nfld.type, nfld.type_name) != (fld.type, fld.type_name):
                changes.append(_mk(loc, "field_type_changed", fld.name, nfld.name, True,
                                   f"{fld.type_name or fld.type} -> {nfld.type_name or nfld.type}"))
        for num in new_fields.keys() - old_fields.keys():
            changes.append(_mk(f"{qname}.{num}", "field_added", None, new_fields[num].name, False))

    for qname in new_enums.keys() - old_enums.keys():
        changes.append(_mk(qname, "enum_added", None, qname, False))
    for qname in old_enums.keys() - new_enums.keys():
        changes.append(_mk(qname, "enum_removed", qname, None, True))

    for qname in old_enums.keys() & new_enums.keys():
        old_vals = {v.number: v for v in old_enums[qname].value}
        new_vals = {v.number: v for v in new_enums[qname].value}
        for num, val in old_vals.items():
            loc = f"{qname}.{num}"
            if num not in new_vals:
                changes.append(_mk(loc, "enum_value_removed", val.name, None, True))
            elif new_vals[num].name != val.name:
                changes.append(_mk(loc, "enum_value_renamed", val.name, new_vals[num].name, True,
                                   "wire-compatible, source-breaking"))
        for num in new_vals.keys() - old_vals.keys():
            changes.append(_mk(f"{qname}.{num}", "enum_value_added", None, new_vals[num].name, False))

    changes.sort(key=lambda c: (c["location"], c["kind"]))
    return changes


def diff_proto_texts(old_text: str, new_text: str) -> list[dict]:
    """Compile (or parse) both proto texts and diff the resulting descriptor sets."""
    return diff_descriptor_sets(to_descriptor_set(old_text), to_descriptor_set(new_text))
