import ast
from pathlib import Path
import re
from typing import Any


def diff_migrations(files: list[tuple[str, str]]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []

    def make_change(kind: str, location: str, old_val: Any = None, new_val: Any = None, breaking: bool = False, note: str = "") -> dict[str, Any]:
        return {
            "id": f"db:{location}:{kind}",
            "surface": "db",
            "kind": kind,
            "location": location,
            "old": old_val,
            "new": new_val,
            "breaking": breaking,
            "note": note,
        }

    update_regex = re.compile(
        r"UPDATE\s+(\w+)\s+SET\s+(\w+)\s*=\s*['\"]([^'\"]+)['\"]\s+WHERE\s+(\w+)\s*=\s*['\"]([^'\"]+)['\"]",
        re.IGNORECASE,
    )

    for filename, content in files:
        file_path_str = Path(filename).name
        try:
            tree = ast.parse(content)
        except Exception:
            continue

        # Find upgrade function
        upgrade_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
                upgrade_func = node
                break

        if not upgrade_func:
            continue

        for stmt in ast.walk(upgrade_func):
            # Check for with op.batch_alter_table('<table>') as batch_op:
            if isinstance(stmt, ast.With):
                for item in stmt.items:
                    expr = item.context_expr
                    batch_var_name = item.optional_vars.id if isinstance(item.optional_vars, ast.Name) else None
                    table_name = None
                    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
                        if expr.func.attr == "batch_alter_table" and expr.args:
                            first_arg = expr.args[0]
                            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                                table_name = first_arg.value

                    if table_name and batch_var_name:
                        for body_stmt in stmt.body:
                            for call_node in ast.walk(body_stmt):
                                if isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Attribute):
                                    if isinstance(call_node.func.value, ast.Name) and call_node.func.value.id == batch_var_name:
                                        _handle_table_call(call_node, table_name, file_path_str, changes, make_change)

            # Direct op.xxx calls
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call_node = stmt.value
                if isinstance(call_node.func, ast.Attribute) and isinstance(call_node.func.value, ast.Name) and call_node.func.value.id == "op":
                    attr = call_node.func.attr
                    if attr == "execute" and call_node.args:
                        arg0 = call_node.args[0]
                        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                            sql = arg0.value.strip()
                            m = update_regex.match(sql)
                            if m:
                                tbl, col_set, val_new, col_where, val_old = m.groups()
                                changes.append(make_change(
                                    "value_renamed",
                                    f"{tbl}.{col_where}.{val_old}",
                                    old_val=val_old,
                                    new_val=val_new,
                                    breaking=True,
                                ))
                            else:
                                line = stmt.lineno
                                changes.append(make_change(
                                    "data_update",
                                    f"{file_path_str}:{line}",
                                    breaking=False,
                                ))
                    elif attr in ("add_column", "drop_column", "alter_column") and call_node.args:
                        arg0 = call_node.args[0]
                        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                            table_name = arg0.value
                            # Shift args so remainder looks like batch_op call
                            _handle_direct_op_call(call_node, table_name, changes, make_change)

    return changes


def _extract_column_name(arg_node: ast.AST) -> str | None:
    if isinstance(arg_node, ast.Constant) and isinstance(arg_node.value, str):
        return arg_node.value
    if isinstance(arg_node, ast.Call):
        # sa.Column("name", ...) or Column("name", ...)
        if arg_node.args and isinstance(arg_node.args[0], ast.Constant) and isinstance(arg_node.args[0].value, str):
            return arg_node.args[0].value
        for kw in arg_node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    return None


def _handle_table_call(call_node: ast.Call, table_name: str, file_path_str: str, changes: list, make_change):
    attr = call_node.func.attr
    if attr == "add_column" and call_node.args:
        col = _extract_column_name(call_node.args[0])
        if col:
            changes.append(make_change(
                "column_added",
                f"{table_name}.{col}",
                new_val=col,
                breaking=False,
            ))
    elif attr == "drop_column" and call_node.args:
        col = _extract_column_name(call_node.args[0])
        if col:
            changes.append(make_change(
                "column_dropped",
                f"{table_name}.{col}",
                old_val=col,
                breaking=True,
            ))
    elif attr == "alter_column" and call_node.args:
        col = _extract_column_name(call_node.args[0])
        new_name = None
        for kw in call_node.keywords:
            if kw.arg == "new_column_name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                new_name = kw.value.value
                break
        if col and new_name:
            changes.append(make_change(
                "column_renamed",
                f"{table_name}.{col}",
                old_val=col,
                new_val=new_name,
                breaking=True,
            ))


def _handle_direct_op_call(call_node: ast.Call, table_name: str, changes: list, make_change):
    attr = call_node.func.attr
    if attr == "add_column" and len(call_node.args) > 1:
        col = _extract_column_name(call_node.args[1])
        if col:
            changes.append(make_change("column_added", f"{table_name}.{col}", new_val=col, breaking=False))
    elif attr == "drop_column" and len(call_node.args) > 1:
        col = _extract_column_name(call_node.args[1])
        if col:
            changes.append(make_change("column_dropped", f"{table_name}.{col}", old_val=col, breaking=True))
    elif attr == "alter_column" and len(call_node.args) > 1:
        col = _extract_column_name(call_node.args[1])
        new_name = None
        for kw in call_node.keywords:
            if kw.arg == "new_column_name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                new_name = kw.value.value
                break
        if col and new_name:
            changes.append(make_change("column_renamed", f"{table_name}.{col}", old_val=col, new_val=new_name, breaking=True))
