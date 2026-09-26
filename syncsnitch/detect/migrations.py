"""DB/Alembic migration drift detection."""
from __future__ import annotations

import ast
import os
from pathlib import Path


def _extract_upgrade_body(source: str) -> ast.FunctionDef | None:
    """Return the AST node for the upgrade() function."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    return None


def _get_string_arg(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _get_call_attr(node: ast.expr) -> str | None:
    """Return the attribute name for a Call whose func is an Attribute."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _first_string_arg(call: ast.Call) -> str | None:
    if call.args:
        return _get_string_arg(call.args[0])
    return None


def _kw(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == name:
            return _get_string_arg(kw.value)
    return None


def _parse_migration_file(source: str, filename: str) -> list[dict]:
    """Parse a single migration file and return Change dicts."""
    upgrade_fn = _extract_upgrade_body(source)
    if upgrade_fn is None:
        return []

    changes: list[dict] = []

    def _process_stmts(stmts: list[ast.stmt], table: str | None = None) -> None:
        for stmt in stmts:
            # with op.batch_alter_table("tbl") as batch_op:
            if isinstance(stmt, ast.With):
                batch_table = _try_extract_batch_table(stmt)
                if batch_table:
                    _process_stmts(stmt.body, batch_table)
                    continue
                # generic with block - recurse
                _process_stmts(stmt.body, table)
                continue

            if not isinstance(stmt, ast.Expr):
                continue
            expr = stmt.value
            if not isinstance(expr, ast.Call):
                continue

            method = _get_call_attr(expr)
            if method is None:
                continue

            if method == "add_column":
                col_name = _extract_add_column_name(expr)
                if col_name:
                    loc = f"{table or 'unknown'}.{col_name}"
                    changes.append({
                        "id": f"db:{loc}:column_added",
                        "surface": "db",
                        "kind": "column_added",
                        "location": loc,
                        "old": None,
                        "new": col_name,
                        "breaking": False,
                        "note": "",
                    })

            elif method == "drop_column":
                col_name = _first_string_arg(expr)
                if col_name is None and len(expr.args) >= 2:
                    col_name = _get_string_arg(expr.args[1])
                if col_name:
                    loc = f"{table or 'unknown'}.{col_name}"
                    changes.append({
                        "id": f"db:{loc}:column_dropped",
                        "surface": "db",
                        "kind": "column_dropped",
                        "location": loc,
                        "old": col_name,
                        "new": None,
                        "breaking": True,
                        "note": "",
                    })

            elif method == "alter_column":
                new_col_name = _kw(expr, "new_column_name")
                if new_col_name:
                    # rename
                    old_col = _first_string_arg(expr)
                    tbl = table or "unknown"
                    loc = f"{tbl}.{old_col}"
                    changes.append({
                        "id": f"db:{loc}:column_renamed",
                        "surface": "db",
                        "kind": "column_renamed",
                        "location": loc,
                        "old": old_col,
                        "new": new_col_name,
                        "breaking": True,
                        "note": "",
                    })

            elif method == "execute":
                sql = _first_string_arg(expr)
                if sql:
                    rename_change = _detect_value_rename_in_sql(sql, table)
                    if rename_change:
                        changes.append(rename_change)
                    else:
                        # generic data_update - non-breaking
                        pass

    def _try_extract_batch_table(node: ast.With) -> str | None:
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Call):
                func = ctx.func
                if (isinstance(func, ast.Attribute) and func.attr == "batch_alter_table"):
                    return _first_string_arg(ctx)
        return None

    def _extract_add_column_name(call: ast.Call) -> str | None:
        # add_column("tbl", sa.Column("name", ...)) or batch_op.add_column(sa.Column("name"...))
        for arg in call.args:
            if isinstance(arg, ast.Call):
                inner = arg
                inner_func = inner.func
                if isinstance(inner_func, ast.Attribute) and inner_func.attr == "Column":
                    if inner.args:
                        return _get_string_arg(inner.args[0])
                elif isinstance(inner_func, ast.Name) and inner_func.id == "Column":
                    if inner.args:
                        return _get_string_arg(inner.args[0])
        return None

    def _detect_value_rename_in_sql(sql: str, table: str | None) -> dict | None:
        # Pattern: UPDATE t SET c = 'NEW' WHERE c = 'OLD'
        import re
        m = re.search(
            r"UPDATE\s+(\w+)\s+SET\s+(\w+)\s*=\s*'([^']+)'\s+WHERE\s+\2\s*=\s*'([^']+)'",
            sql,
            re.IGNORECASE,
        )
        if m:
            tbl, col, new_val, old_val = m.groups()
            loc = f"{tbl}.{col}"
            return {
                "id": f"db:{loc}:value_renamed",
                "surface": "db",
                "kind": "value_renamed",
                "location": loc,
                "old": old_val,
                "new": new_val,
                "breaking": True,
                "note": "",
            }
        return None

    _process_stmts(upgrade_fn.body)
    return changes


def diff_migrations(files: list[str]) -> list[dict]:
    """
    Parse a list of migration file *contents* (strings) in order and
    return aggregated Change dicts from all upgrade() functions.
    """
    changes: list[dict] = []
    for content in files:
        changes.extend(_parse_migration_file(content, ""))
    return changes


def diff_migration_files(paths: list[str]) -> list[dict]:
    """Load files from disk paths and call diff_migrations."""
    contents = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            contents.append(fh.read())
    return diff_migrations(contents)
