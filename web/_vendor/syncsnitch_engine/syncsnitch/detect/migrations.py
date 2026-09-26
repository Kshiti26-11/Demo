"""DB/Alembic migration drift detection (ast on each file's upgrade() only)."""
from __future__ import annotations

import ast
import re

_VALUE_RENAME = re.compile(
    r"UPDATE\s+(\w+)\s+SET\s+(\w+)\s*=\s*'([^']*)'\s+WHERE\s+\2\s*=\s*'([^']*)'\s*;?\s*$",
    re.IGNORECASE,
)


def _str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _kw(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == name:
            return _str(kw.value)
    return None


def _column_name(node: ast.expr) -> str | None:
    """Name from sa.Column("name", ...) / Column("name", ...)."""
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr == "Column") or (
            isinstance(func, ast.Name) and func.id == "Column"
        ):
            return _str(node.args[0])
    return None


def _change(kind: str, location: str, old, new, breaking: bool, note: str = "") -> dict:
    return {
        "id": f"db:{location}:{kind}",
        "surface": "db",
        "kind": kind,
        "location": location,
        "old": old,
        "new": new,
        "breaking": breaking,
        "note": note,
    }


def _batch_table(node: ast.With) -> tuple[str, str] | None:
    """(alias, table) for "with op.batch_alter_table('<table>') as batch_op:"."""
    for item in node.items:
        ctx = item.context_expr
        if (
            isinstance(ctx, ast.Call)
            and isinstance(ctx.func, ast.Attribute)
            and ctx.func.attr == "batch_alter_table"
            and isinstance(item.optional_vars, ast.Name)
        ):
            table = _str(ctx.args[0]) if ctx.args else _kw(ctx, "table_name")
            if table:
                return item.optional_vars.id, table
    return None


def _parse_file(filename: str, source: str) -> list[dict]:
    tree = ast.parse(source)
    upgrade = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"),
        None,
    )
    if upgrade is None:
        return []

    changes: list[dict] = []

    def handle_call(call: ast.Call, batches: dict[str, str]) -> None:
        func = call.func
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
            return
        receiver, method = func.value.id, func.attr
        if receiver in batches:  # batch_op.<method>(...) - the table comes from the with-block
            table, args = batches[receiver], list(call.args)
        elif receiver == "op":  # op.<method>(<table>, ...)
            table, args = _str(call.args[0]) if call.args else None, list(call.args[1:])
        else:
            return

        if method == "add_column" and table and args:
            col = _column_name(args[0])
            if col:
                changes.append(_change("column_added", f"{table}.{col}", None, col, False))
        elif method == "drop_column" and table and args:
            col = _str(args[0])
            if col:
                changes.append(_change("column_dropped", f"{table}.{col}", col, None, True))
        elif method == "alter_column" and table and args:
            col, new_name = _str(args[0]), _kw(call, "new_column_name")
            if col and new_name:
                changes.append(_change("column_renamed", f"{table}.{col}", col, new_name, True))
        elif method == "execute" and receiver == "op":
            sql = _str(call.args[0]) if call.args else None
            match = _VALUE_RENAME.search(sql.strip()) if sql else None
            if match:
                tbl, col, new_val, old_val = match.groups()
                changes.append(_change("value_renamed", f"{tbl}.{col}.{old_val}", old_val, new_val, True))
            else:
                changes.append(_change("data_update", f"{filename}:{call.lineno}", None, sql, False))

    def walk(stmts: list[ast.stmt], batches: dict[str, str]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.With):
                found = _batch_table(stmt)
                walk(stmt.body, {**batches, found[0]: found[1]} if found else batches)
            elif isinstance(stmt, (ast.If, ast.For, ast.While, ast.Try)):
                for block in ("body", "orelse", "finalbody"):
                    walk(getattr(stmt, block, []) or [], batches)
                for handler in getattr(stmt, "handlers", []) or []:
                    walk(handler.body, batches)
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                handle_call(stmt.value, batches)

    walk(upgrade.body, {})
    return changes


def diff_migrations(files: list[tuple[str, str]] | list[str]) -> list[dict]:
    """
    Changes from the upgrade() of every migration file, in order.
    ``files`` is a list of (file name, source) tuples; plain source strings are accepted too.
    """
    changes: list[dict] = []
    for i, item in enumerate(files):
        name, source = item if isinstance(item, tuple) else (f"migration_{i}.py", item)
        changes.extend(_parse_file(name.rsplit("/", 1)[-1], source))
    return changes
