"""REST/OpenAPI drift detection."""
from __future__ import annotations

import yaml
from typing import Any


def _load(text: str) -> dict:
    return yaml.safe_load(text)


def _resolve_ref(schema: dict, root: dict) -> dict:
    """Follow a single $ref in the schema root."""
    ref = schema.get("$ref", "")
    if ref.startswith("#/"):
        parts = ref.lstrip("#/").split("/")
        node = root
        for part in parts:
            node = node[part]
        return node
    return schema


def _get_schemas(doc: dict) -> dict[str, Any]:
    return doc.get("components", {}).get("schemas", {})


def _get_enum(schema: dict, root: dict) -> list | None:
    resolved = _resolve_ref(schema, root)
    return resolved.get("enum")


def _get_properties(schema: dict, root: dict) -> dict:
    resolved = _resolve_ref(schema, root)
    return resolved.get("properties", {})


def _get_required(schema: dict, root: dict) -> set:
    resolved = _resolve_ref(schema, root)
    return set(resolved.get("required", []))


def _get_type(schema: dict, root: dict) -> str | None:
    resolved = _resolve_ref(schema, root)
    return resolved.get("type")


def diff_openapi(old_text: str, new_text: str) -> list[dict]:
    """Compare two OpenAPI YAML texts and return a list of Change dicts."""
    old_doc = _load(old_text)
    new_doc = _load(new_text)

    old_schemas = _get_schemas(old_doc)
    new_schemas = _get_schemas(new_doc)

    changes: list[dict] = []

    # schema_added / schema_removed
    for name in new_schemas:
        if name not in old_schemas:
            changes.append({
                "id": f"rest:{name}:schema_added",
                "surface": "rest",
                "kind": "schema_added",
                "location": name,
                "old": None,
                "new": name,
                "breaking": False,
                "note": "",
            })

    for name in old_schemas:
        if name not in new_schemas:
            changes.append({
                "id": f"rest:{name}:schema_removed",
                "surface": "rest",
                "kind": "schema_removed",
                "location": name,
                "old": name,
                "new": None,
                "breaking": True,
                "note": "",
            })

    # per-schema property/enum comparison
    for name in old_schemas:
        if name not in new_schemas:
            continue

        old_schema = old_schemas[name]
        new_schema = new_schemas[name]

        # enum comparison
        old_enum = _get_enum(old_schema, old_doc)
        new_enum = _get_enum(new_schema, new_doc)
        if old_enum is not None and new_enum is not None:
            old_set = set(old_enum)
            new_set = set(new_enum)
            for val in old_set - new_set:
                changes.append({
                    "id": f"rest:{name}.{val}:enum_value_removed",
                    "surface": "rest",
                    "kind": "enum_value_removed",
                    "location": f"{name}.{val}",
                    "old": val,
                    "new": None,
                    "breaking": True,
                    "note": "",
                })
            for val in new_set - old_set:
                changes.append({
                    "id": f"rest:{name}.{val}:enum_value_added",
                    "surface": "rest",
                    "kind": "enum_value_added",
                    "location": f"{name}.{val}",
                    "old": None,
                    "new": val,
                    "breaking": False,
                    "note": "consumers with exhaustive status handling may break",
                })

        # property comparison
        old_props = _get_properties(old_schema, old_doc)
        new_props = _get_properties(new_schema, new_doc)
        old_required = _get_required(old_schema, old_doc)
        new_required = _get_required(new_schema, new_doc)

        for prop in old_props:
            if prop not in new_props:
                changes.append({
                    "id": f"rest:{name}.{prop}:property_removed",
                    "surface": "rest",
                    "kind": "property_removed",
                    "location": f"{name}.{prop}",
                    "old": prop,
                    "new": None,
                    "breaking": True,
                    "note": "",
                })
            else:
                old_type = _get_type(old_props[prop], old_doc)
                new_type = _get_type(new_props[prop], new_doc)
                if old_type is not None and new_type is not None and old_type != new_type:
                    changes.append({
                        "id": f"rest:{name}.{prop}:type_changed",
                        "surface": "rest",
                        "kind": "type_changed",
                        "location": f"{name}.{prop}",
                        "old": old_type,
                        "new": new_type,
                        "breaking": True,
                        "note": "",
                    })

        for prop in new_props:
            if prop not in old_props:
                is_required = prop in new_required
                changes.append({
                    "id": f"rest:{name}.{prop}:property_added",
                    "surface": "rest",
                    "kind": "property_added",
                    "location": f"{name}.{prop}",
                    "old": None,
                    "new": prop,
                    "breaking": False,
                    "note": f"{'required' if is_required else 'optional'} property added",
                })

    return changes
