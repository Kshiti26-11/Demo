"""Python AST scanner: usages of changed contract tokens, plus the route/reference graph used for endpoints."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@dataclass
class PyFileIndex:
    """What one .py file contributes to the consumer-wide graph."""

    hits: list[dict] = field(default_factory=list)
    routes: dict[str, list[str]] = field(default_factory=dict)  # function name -> ["METHOD /path"]
    references: dict[str, set[str]] = field(default_factory=dict)  # symbol -> names it references
    constants: list[tuple[str, str]] = field(default_factory=list)  # (symbol, string constant)


def _route(deco: ast.expr) -> str | None:
    if (
        isinstance(deco, ast.Call)
        and isinstance(deco.func, ast.Attribute)
        and deco.func.attr.lower() in _HTTP_METHODS
        and deco.args
        and isinstance(deco.args[0], ast.Constant)
        and isinstance(deco.args[0].value, str)
    ):
        return f"{deco.func.attr.upper()} {deco.args[0].value}"
    return None


def _names_used(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def scan_python_file(source: str, file_path: str, tokens: dict[str, list[str]]) -> PyFileIndex:
    """
    Hits for every token (usage kinds: subscript, get_call, attribute, model_field, keyword, literal,
    embedded_text) plus routes, references and string constants for the consumer-wide endpoint graph.
    ``tokens`` maps token -> change ids. Hit endpoints are filled in later by trace_consumer.
    """
    index = PyFileIndex()
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return index

    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    module_symbols: dict[int, str] = {}  # top-level "NAME = ..." statements
    for stmt in tree.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target] if isinstance(stmt, ast.AnnAssign) else []
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        if names:
            module_symbols[id(stmt)] = names[0]
            index.references.setdefault(names[0], set()).update(_names_used(stmt.value) if stmt.value else set())

    def symbol_of(node: ast.AST) -> str:
        current = node
        while id(current) in parents:
            parent = parents[id(current)]
            if isinstance(parent, _SCOPES):
                return parent.name
            if id(parent) in module_symbols:
                return module_symbols[id(parent)]
            current = parent
        return module_symbols.get(id(node), "<module>")

    for node in ast.walk(tree):
        if isinstance(node, _SCOPES):
            index.references.setdefault(node.name, set()).update(_names_used(node) - {node.name})
            if not isinstance(node, ast.ClassDef):
                for deco in node.decorator_list:
                    route = _route(deco)
                    if route:
                        index.routes.setdefault(node.name, []).append(route)

    seen: set[tuple[int, str, str]] = set()

    def add(token: str, line: int, kind: str, node: ast.AST) -> None:
        if (line, token, kind) in seen:
            return
        seen.add((line, token, kind))
        index.hits.append({
            "file": file_path,
            "line": line,
            "token": token,
            "change_ids": tokens[token],
            "usage_kind": kind,
            "symbol": symbol_of(node),
            "endpoints": [],
            "in_tests": file_path.startswith("tests/"),
        })

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value in tokens:
                add(key.value, node.lineno, "subscript", node)
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in tokens
            ):
                add(node.args[0].value, node.lineno, "get_call", node)
            for kw in node.keywords:
                if kw.arg in tokens:
                    add(kw.arg, kw.value.lineno, "keyword", node)
        elif isinstance(node, ast.Attribute) and node.attr in tokens:
            add(node.attr, node.lineno, "attribute", node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in tokens:
            add(node.target.id, node.lineno, "model_field", node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            index.constants.append((symbol_of(node), node.value))
            if node.value in tokens:
                add(node.value, node.lineno, "literal", node)
                continue
            for tok in tokens:
                if len(node.value) > len(tok) and re.search(rf"\b{re.escape(tok)}\b", node.value):
                    add(tok, node.lineno, "embedded_text", node)

    return index
