from typing import Any
import yaml


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        return {}
    parts = ref.lstrip("#/").split("/")
    cur: Any = spec
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return {}
    return cur if isinstance(cur, dict) else {}


def diff_openapi(old_text: str, new_text: str) -> list[dict[str, Any]]:
    old_spec = yaml.safe_load(old_text) or {}
    new_spec = yaml.safe_load(new_text) or {}

    old_schemas = old_spec.get("components", {}).get("schemas", {})
    new_schemas = new_spec.get("components", {}).get("schemas", {})

    changes: list[dict[str, Any]] = []

    def make_change(kind: str, location: str, old: Any = None, new: Any = None, breaking: bool = False, note: str = "") -> dict[str, Any]:
        return {
            "id": f"rest:{location}:{kind}",
            "surface": "rest",
            "kind": kind,
            "location": location,
            "old": old,
            "new": new,
            "breaking": breaking,
            "note": note,
        }

    # Schemas added / removed
    for name in sorted(new_schemas.keys()):
        if name not in old_schemas:
            changes.append(make_change("schema_added", name, new=name, breaking=False))

    for name in sorted(old_schemas.keys()):
        if name not in new_schemas:
            changes.append(make_change("schema_removed", name, old=name, breaking=True))

    # Compare common schemas
    common_schemas = sorted(set(old_schemas.keys()) & set(new_schemas.keys()))
    for name in common_schemas:
        old_s = old_schemas[name]
        new_s = new_schemas[name]

        # Enums
        old_enum = old_s.get("enum")
        new_enum = new_s.get("enum")
        if old_enum is not None or new_enum is not None:
            old_vals = old_enum or []
            new_vals = new_enum or []
            for val in old_vals:
                if val not in new_vals:
                    changes.append(make_change(
                        "enum_value_removed",
                        f"{name}.{val}",
                        old=val,
                        breaking=True,
                    ))
            for val in new_vals:
                if val not in old_vals:
                    changes.append(make_change(
                        "enum_value_added",
                        f"{name}.{val}",
                        new=val,
                        breaking=False,
                        note="consumers with exhaustive status handling may break",
                    ))

        # Properties
        old_props = old_s.get("properties", {})
        new_props = new_s.get("properties", {})
        new_required = new_s.get("required", [])

        for prop, pdef in sorted(old_props.items()):
            if prop not in new_props:
                changes.append(make_change(
                    "property_removed",
                    f"{name}.{prop}",
                    old=prop,
                    breaking=True,
                ))

        for prop, pdef in sorted(new_props.items()):
            if prop not in old_props:
                note = "required" if prop in new_required else "optional"
                changes.append(make_change(
                    "property_added",
                    f"{name}.{prop}",
                    new=prop,
                    breaking=False,
                    note=note,
                ))

        for prop in sorted(set(old_props.keys()) & set(new_props.keys())):
            old_p = old_props[prop]
            new_p = new_props[prop]
            # Check type or $ref target
            old_type = old_p.get("type") or old_p.get("$ref")
            new_type = new_p.get("type") or new_p.get("$ref")
            if old_type != new_type:
                changes.append(make_change(
                    "type_changed",
                    f"{name}.{prop}",
                    old=old_type,
                    new=new_type,
                    breaking=True,
                ))

    return changes
