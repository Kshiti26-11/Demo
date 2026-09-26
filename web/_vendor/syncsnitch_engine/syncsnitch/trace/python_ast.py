import ast
from collections import defaultdict
from pathlib import Path
import re
from typing import Any


class SymbolVisitor(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.scope_stack: list[str] = []
        self.routes: dict[str, str] = {}  # symbol_name -> "METHOD /path"
        self.references: dict[str, set[str]] = defaultdict(set)  # symbol_name -> set of referenced names
        self.current_symbol: str = "<module>"

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_func(node)

    def _handle_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        # Check decorators for route: @app.get("/path"), @router.post("/path"), etc.
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                attr = dec.func.attr.lower()
                if attr in ("get", "post", "put", "patch", "delete") and dec.args:
                    arg0 = dec.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                        self.routes[node.name] = f"{attr.upper()} {arg0.value}"

        prev_symbol = self.current_symbol
        self.current_symbol = node.name
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.current_symbol = prev_symbol

    def visit_ClassDef(self, node: ast.ClassDef):
        prev_symbol = self.current_symbol
        self.current_symbol = node.name
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.current_symbol = prev_symbol

    def visit_Assign(self, node: ast.Assign):
        # Module-level assignments: NAME = ...
        if not self.scope_stack:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    prev = self.current_symbol
                    self.current_symbol = target.id
                    self.visit(node.value)
                    self.current_symbol = prev
                    return
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if self.current_symbol:
            self.references[self.current_symbol].add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if self.current_symbol:
            self.references[self.current_symbol].add(node.attr)
        self.generic_visit(node)


class TokenVisitor(ast.NodeVisitor):
    def __init__(self, token_map: dict[str, list[str]], filename: str, endpoint_resolver: Any):
        self.token_map = token_map  # token -> list[change_id]
        self.filename = filename
        self.endpoint_resolver = endpoint_resolver
        self.scope_stack: list[str] = []
        self.module_assign_target: str | None = None
        self.hits: list[dict[str, Any]] = []

    def _get_symbol(self) -> str:
        if self.scope_stack:
            return self.scope_stack[-1]
        if self.module_assign_target:
            return self.module_assign_target
        return "<module>"

    def _add_hit(self, line: int, token: str, usage_kind: str):
        if token in self.token_map:
            sym = self._get_symbol()
            endpoints = self.endpoint_resolver(sym, self.filename)
            self.hits.append({
                "file": Path(self.filename).as_posix(),
                "line": line,
                "token": token,
                "change_ids": self.token_map[token],
                "usage_kind": usage_kind,
                "symbol": sym,
                "endpoints": endpoints,
                "in_tests": Path(self.filename).as_posix().startswith("tests/"),
            })

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef):
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Assign(self, node: ast.Assign):
        if not self.scope_stack:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.module_assign_target = target.id
                    break
        self.generic_visit(node)
        self.module_assign_target = None

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            tok = node.target.id
            if tok in self.token_map:
                self._add_hit(node.lineno, tok, "model_field")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript):
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            tok = node.slice.value
            if tok in self.token_map:
                self._add_hit(node.lineno, tok, "subscript")
                # Avoid matching slice again as generic literal
                self.visit(node.value)
                return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # .get("<token>")
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                tok = first_arg.value
                if tok in self.token_map:
                    self._add_hit(node.lineno, tok, "get_call")
                    self.visit(node.func.value)
                    for a in node.args[1:]:
                        self.visit(a)
                    for kw in node.keywords:
                        self.visit(kw)
                    return

        # Keyword arguments: foo(token=...)
        for kw in node.keywords:
            if kw.arg and kw.arg in self.token_map:
                self._add_hit(node.lineno, kw.arg, "keyword")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in self.token_map:
            self._add_hit(node.lineno, node.attr, "attribute")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str):
            text = node.value
            if text in self.token_map:
                self._add_hit(node.lineno, text, "literal")
            else:
                for tok in self.token_map:
                    if len(tok) < len(text) and re.search(rf"\b{re.escape(tok)}\b", text):
                        self._add_hit(node.lineno, tok, "embedded_text")
        self.generic_visit(node)


def build_endpoint_resolver(file_contents: dict[str, str]):
    """Build cross-file reference graph and return a function resolver(symbol, filename) -> list[str]."""
    all_routes: dict[str, str] = {}  # symbol -> route string
    callers: dict[str, set[str]] = defaultdict(set)  # referenced_name -> set of caller symbol names

    for path, content in file_contents.items():
        try:
            tree = ast.parse(content, filename=path)
        except Exception:
            continue
        vis = SymbolVisitor(path)
        vis.visit(tree)
        for sym, route in vis.routes.items():
            all_routes[sym] = route
        for caller, referenced in vis.references.items():
            for ref in referenced:
                callers[ref].add(caller)

    def resolve(symbol: str, filename: str) -> list[str]:
        routes_found = set()
        if symbol in all_routes:
            routes_found.add(all_routes[symbol])

        # BFS up to 3 hops
        visited = {symbol}
        current_level = {symbol}
        for hop in range(3):
            next_level = set()
            for s in current_level:
                for parent in callers.get(s, []):
                    if parent in all_routes:
                        routes_found.add(all_routes[parent])
                    if parent not in visited:
                        visited.add(parent)
                        next_level.add(parent)
            current_level = next_level

        return sorted(routes_found)

    return resolve


def scan_python_file(path: Path, relative_path: str, token_map: dict[str, list[str]], resolver: Any) -> list[dict[str, Any]]:
    try:
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=relative_path)
    except Exception:
        return []

    visitor = TokenVisitor(token_map, relative_path, resolver)
    visitor.visit(tree)
    return visitor.hits
