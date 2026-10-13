"""Gate 1: static checks with ast (no execution)."""
from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass
class StaticResult:
    ok: bool
    check: str | None = None  # C1 | C2 | C3
    reason: str | None = None

    @property
    def problem(self) -> str | None:
        return None if self.ok else f"{self.check}: {self.reason}"


def _test_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            out.append(node)
    return out


def _import_aliases(tree: ast.Module, module: str, target: str) -> tuple[set[str], set[str]]:
    """Return (names bound to the target, names bound to the target's module)."""
    names: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module and node.level == 0:
            for alias in node.names:
                if alias.name == target:
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    modules.add(alias.asname or alias.name.split(".")[0])
    return names, modules


def _calls_in(node: ast.AST):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            yield sub


def _is_target_call(call: ast.Call, fn: dict, names: set[str], modules: set[str]) -> bool:
    f = call.func
    if fn.get("is_method"):
        if fn["name"] == "__init__":
            return (isinstance(f, ast.Name) and f.id in names) or (
                isinstance(f, ast.Attribute) and f.attr == fn["class_name"])
        return isinstance(f, ast.Attribute) and f.attr == fn["name"]
    if isinstance(f, ast.Name):
        return f.id in names
    if isinstance(f, ast.Attribute) and f.attr == fn["name"]:
        return True
    return False


_NON_CONST = (ast.Name, ast.Call, ast.Attribute, ast.Subscript, ast.Starred)


def _is_meaningful_assert(node: ast.Assert) -> bool:
    return any(isinstance(sub, _NON_CONST) for sub in ast.walk(node.test))


def _is_raises_block(node: ast.With | ast.AsyncWith) -> bool:
    for item in node.items:
        expr = item.context_expr
        if isinstance(expr, ast.Call):
            f = expr.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if name == "raises" and any(isinstance(s, ast.Call) for b in node.body for s in ast.walk(b)):
                return True
    return False


def static_check(code: str, fn: dict) -> StaticResult:
    """Apply C1 (syntax), C2 (targets the function), C3 (meaningful assertion)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return StaticResult(False, "C1", f"invalid syntax: {exc.msg} (line {exc.lineno})")
    tests = _test_functions(tree)
    if not tests:
        return StaticResult(False, "C2", "does not call target: no test functions (def test_...) found")
    target = fn["class_name"] if fn.get("is_method") else fn["name"]
    names, modules = _import_aliases(tree, fn["module"], target)
    if not names and not modules:
        return StaticResult(False, "C2", f"does not call target: missing `from {fn['module']} import {target}`")
    if fn.get("is_method") and fn["name"] != "__init__":
        uses_class = any(isinstance(n, ast.Name) and n.id in names for n in ast.walk(tree)) or bool(modules)
        if not uses_class:
            return StaticResult(False, "C2", f"does not call target: never creates a {target} instance")
    calling = [t for t in tests if any(_is_target_call(c, fn, names, modules) for c in _calls_in(t))]
    if not calling:
        return StaticResult(False, "C2", f"does not call target: no test calls {fn['qualname']}")
    meaningful = False
    for t in tests:
        for sub in ast.walk(t):
            if isinstance(sub, ast.Assert) and _is_meaningful_assert(sub):
                meaningful = True
            elif isinstance(sub, (ast.With, ast.AsyncWith)) and _is_raises_block(sub):
                meaningful = True
    if not meaningful:
        return StaticResult(False, "C3", "trivial test: no assert or pytest.raises involving the call result "
                                         "(asserts on constants only, e.g. `assert True`)")
    return StaticResult(True)


def test_function_names(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("test")]


def test_function_sources(code: str) -> dict[str, str]:
    """Map test function name -> its source segment (decorators included)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    lines = code.splitlines(keepends=True)
    out = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"):
            start = min([n.lineno] + [d.lineno for d in n.decorator_list])
            out[n.name] = "".join(lines[start - 1:n.end_lineno]).rstrip() + "\n"
    return out


def keep_only_tests(code: str, keep: set[str]) -> str:
    """Remove top-level test functions not in ``keep`` (used to build accepted test files)."""
    tree = ast.parse(code)
    lines = code.splitlines(keepends=True)
    drop: set[int] = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test") and n.name not in keep:
            start = min([n.lineno] + [d.lineno for d in n.decorator_list])
            drop.update(range(start, n.end_lineno + 1))
    text = "".join(line for i, line in enumerate(lines, start=1) if i not in drop)
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    return text.rstrip() + "\n"
