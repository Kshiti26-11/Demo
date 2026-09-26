"""Python AST scanner: finds usages of changed contract tokens."""
from __future__ import annotations

import ast
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Route extraction helpers
# ---------------------------------------------------------------------------

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _extract_routes(tree: ast.Module) -> dict[str, list[str]]:
    """
    Return a mapping of function_name -> [list of route strings like 'POST /foo/{id}'].
    Looks for @<obj>.get/post/put/patch/delete("<path>") decorators.
    """
    routes: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fn_name = node.name
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            func = deco.func
            if not isinstance(func, ast.Attribute):
                continue
            method = func.attr.lower()
            if method not in _HTTP_METHODS:
                continue
            path_arg = None
            if deco.args:
                a = deco.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    path_arg = a.value
            if path_arg:
                key = fn_name
                routes.setdefault(key, [])
                routes[key].append(f"{method.upper()} {path_arg}")
    return routes


def _build_call_graph(tree: ast.Module) -> dict[str, set[str]]:
    """Return {caller_fn -> {callee_names}} from simple Name/Attribute calls."""
    graph: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        callees: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Name):
                callees.add(func.id)
            elif isinstance(func, ast.Attribute):
                callees.add(func.attr)
        graph[node.name] = callees
    return graph


def _reachable_endpoints(
    start: str,
    routes: dict[str, list[str]],
    call_graph: dict[str, set[str]],
    max_hops: int = 3,
) -> list[str]:
    """BFS up to max_hops hops, collect endpoints reachable from start symbol."""
    visited: set[str] = set()
    queue = [start]
    endpoints: list[str] = []
    hops = 0
    while queue and hops <= max_hops:
        next_queue: list[str] = []
        for fn in queue:
            if fn in visited:
                continue
            visited.add(fn)
            endpoints.extend(routes.get(fn, []))
            for callee in call_graph.get(fn, set()):
                if callee not in visited:
                    next_queue.append(callee)
        queue = next_queue
        hops += 1
    return sorted(set(endpoints))


# ---------------------------------------------------------------------------
# Symbol context helpers
# ---------------------------------------------------------------------------

def _innermost_symbol(node: ast.AST, tree: ast.Module) -> str:
    """Return the innermost enclosing function or class name; else module-level assignment."""
    # Build parent map
    parent_map: dict[int, ast.AST] = {}
    for n in ast.walk(tree):
        for child in ast.iter_child_nodes(n):
            parent_map[id(child)] = n

    # Walk up from node
    current = node
    while True:
        parent = parent_map.get(id(current))
        if parent is None:
            break
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return parent.name
        current = parent
    return "<module>"


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

def scan_python_file(
    source: str,
    file_path: str,
    tokens: list[str],
    change_ids_by_token: dict[str, list[str]],
) -> list[dict]:
    """
    Scan a Python source file for usages of the given tokens.
    Returns a list of Hit dicts.
    """
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []

    routes = _extract_routes(tree)
    call_graph = _build_call_graph(tree)

    hits: list[dict] = []

    # Build parent map once
    parent_map: dict[int, ast.AST] = {}
    for n in ast.walk(tree):
        for child in ast.iter_child_nodes(n):
            parent_map[id(child)] = n

    def _symbol_for(node: ast.AST) -> str:
        current = node
        while True:
            parent = parent_map.get(id(current))
            if parent is None:
                break
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return parent.name
            current = parent
        return "<module>"

    def _add_hit(token: str, line: int, usage_kind: str, symbol: str) -> None:
        endpoints = _reachable_endpoints(symbol, routes, call_graph)
        hits.append({
            "file": file_path,
            "line": line,
            "token": token,
            "change_ids": change_ids_by_token.get(token, []),
            "usage_kind": usage_kind,
            "symbol": symbol,
            "endpoints": endpoints,
            "in_tests": file_path.startswith("tests/") or "/tests/" in file_path,
        })

    token_set = set(tokens)

    for node in ast.walk(tree):
        # Subscript: obj["token"]
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                tok = node.slice.value
                if tok in token_set:
                    sym = _symbol_for(node)
                    _add_hit(tok, node.lineno, "subscript", sym)

        # Call: obj.get("token")
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                tok = node.args[0].value
                if tok in token_set:
                    sym = _symbol_for(node)
                    _add_hit(tok, node.lineno, "get_call", sym)

        # Attribute access: obj.token
        elif isinstance(node, ast.Attribute):
            if node.attr in token_set:
                sym = _symbol_for(node)
                _add_hit(node.attr, node.lineno, "attribute", sym)

        # AnnAssign: name: Type = ...
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id in token_set:
                sym = _symbol_for(node)
                _add_hit(target.id, node.lineno, "model_field", sym)

        # keyword argument: func(token=...)
        elif isinstance(node, ast.keyword):
            if node.arg and node.arg in token_set:
                # Get line from parent
                sym = _symbol_for(node)
                line = getattr(node, "lineno", 0)
                _add_hit(node.arg, line, "keyword", sym)

        # String constant (exact match or longer whole-word)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            for tok in token_set:
                if val == tok:
                    sym = _symbol_for(node)
                    _add_hit(tok, node.lineno, "literal", sym)
                elif (
                    len(val) > len(tok)
                    and re.search(r"\b" + re.escape(tok) + r"\b", val)
                ):
                    sym = _symbol_for(node)
                    _add_hit(tok, node.lineno, "embedded_text", sym)

        # Module-level assignment: NAME = ...
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in token_set:
                    sym = _symbol_for(node)
                    _add_hit(tgt.id, node.lineno, "attribute", sym)

    return hits
