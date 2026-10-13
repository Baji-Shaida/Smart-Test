"""AST based function extraction and call-site counting."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SKIP_DIRS = {
    ".git", "venv", ".venv", "env", ".env", "node_modules", "__pycache__", "site-packages",
    ".tox", ".nox", ".mypy_cache", ".pytest_cache", "build", "dist", ".eggs",
}


def is_test_file(rel: str) -> bool:
    """True for files that belong to the project's test suite (used only for coverage)."""
    parts = PurePosixPath(rel).parts
    name = parts[-1]
    if any(p in ("tests", "test") for p in parts[:-1]):
        return True
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def iter_python_files(root: Path, include_tests: bool = False) -> list[str]:
    """Return repo-relative POSIX paths of .py files, skipping vendored/virtualenv folders."""
    root = Path(root)
    out: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(root).parts
        if any(p in SKIP_DIRS or p.endswith(".egg-info") for p in rel_parts[:-1]):
            continue
        rel = PurePosixPath(*rel_parts).as_posix()
        if not include_tests and is_test_file(rel):
            continue
        out.append(rel)
    return out


def module_name_for(rel: str) -> str:
    """Dotted import path for a repo-relative file, handling a src/ layout."""
    parts = list(PurePosixPath(rel).with_suffix("").parts)
    if parts and parts[0] == "src" and len(parts) > 1:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


@dataclass
class ExtractionResult:
    functions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    trees: dict[str, ast.Module] = field(default_factory=dict)


def _unparse(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    a = fn.args
    parts: list[str] = []
    positional = a.posonlyargs + a.args
    defaults = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
    for i, (arg, default) in enumerate(zip(positional, defaults)):
        text = arg.arg + (f": {ast.unparse(arg.annotation)}" if arg.annotation else "")
        if default is not None:
            text += f" = {ast.unparse(default)}" if arg.annotation else f"={ast.unparse(default)}"
        parts.append(text)
        if a.posonlyargs and i == len(a.posonlyargs) - 1:
            parts.append("/")
    if a.vararg:
        parts.append("*" + a.vararg.arg + (f": {ast.unparse(a.vararg.annotation)}" if a.vararg.annotation else ""))
    elif a.kwonlyargs:
        parts.append("*")
    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        text = arg.arg + (f": {ast.unparse(arg.annotation)}" if arg.annotation else "")
        if default is not None:
            text += f" = {ast.unparse(default)}" if arg.annotation else f"={ast.unparse(default)}"
        parts.append(text)
    if a.kwarg:
        parts.append("**" + a.kwarg.arg + (f": {ast.unparse(a.kwarg.annotation)}" if a.kwarg.annotation else ""))
    sig = f"{fn.name}({', '.join(parts)})"
    if fn.returns is not None:
        sig += f" -> {ast.unparse(fn.returns)}"
    return sig


def _body_without_docstring(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def _is_self_assignment(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Assign):
        return all(isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"
                   for t in stmt.targets)
    if isinstance(stmt, ast.AnnAssign):
        t = stmt.target
        return isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        func = stmt.value.func  # super().__init__(...)
        return (isinstance(func, ast.Attribute) and func.attr == "__init__"
                and isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name)
                and func.value.func.id == "super")
    return False


def _decorator_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    return [ast.unparse(d) for d in fn.decorator_list]


def is_trivial(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = _body_without_docstring(fn)
    if not body:
        return True
    if all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                       and s.value.value is Ellipsis) for s in body):
        return True
    if any(d.split("(")[0].split(".")[-1] in ("abstractmethod", "abstractproperty")
           for d in _decorator_names(fn)):
        return True
    if len(body) == 1 and isinstance(body[0], ast.Raise) and body[0].exc is not None \
            and "NotImplementedError" in ast.unparse(body[0].exc):
        return True
    if fn.name in ("__repr__", "__str__") and len(body) == 1 and isinstance(body[0], ast.Return):
        return True
    if fn.name == "__init__" and all(_is_self_assignment(s) for s in body):
        return True
    return False


def _import_lines(tree: ast.Module, source_lines: list[str]) -> list[str]:
    out = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.append("".join(source_lines[node.lineno - 1:node.end_lineno]).rstrip())
    return out


def _class_context(cls: ast.ClassDef) -> str:
    bases = ", ".join(ast.unparse(b) for b in cls.bases)
    header = f"class {cls.name}({bases}):" if bases else f"class {cls.name}:"
    lines = [header]
    doc = ast.get_docstring(cls)
    if doc:
        lines.append(f'    """{doc.splitlines()[0]}"""')
    init = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None)
    if init is not None:
        lines.append(f"    def {_signature(init)}: ...")
        attrs = [ast.unparse(s) for s in _body_without_docstring(init) if _is_self_assignment(s)][:8]
        lines.extend(f"        {a}" for a in attrs)
    else:
        lines.append("    # no __init__ (instantiate with no arguments)")
    methods = [n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if methods:
        lines.append(f"    # methods: {', '.join(methods)}")
    return "\n".join(lines)


def _record(rel: str, fn: ast.FunctionDef | ast.AsyncFunctionDef, source_lines: list[str],
            imports: list[str], cls: ast.ClassDef | None) -> dict:
    qualname = f"{cls.name}.{fn.name}" if cls else fn.name
    start = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
    body = _body_without_docstring(fn)
    body_start = body[0].lineno if body else fn.lineno
    a = fn.args
    all_args = a.posonlyargs + a.args + ([a.vararg] if a.vararg else []) + a.kwonlyargs + ([a.kwarg] if a.kwarg else [])
    positional = a.posonlyargs + a.args
    defaults = {
        arg.arg: ast.unparse(d)
        for arg, d in zip(positional[len(positional) - len(a.defaults):], a.defaults)
    }
    defaults.update({arg.arg: ast.unparse(d) for arg, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None})
    return {
        "id": f"{rel}::{qualname}",
        "file": rel,
        "module": module_name_for(rel),
        "name": fn.name,
        "qualname": qualname,
        "class_name": cls.name if cls else None,
        "line_start": start,
        "line_end": fn.end_lineno,
        "body_start": body_start,
        "is_method": cls is not None,
        "is_async": isinstance(fn, ast.AsyncFunctionDef),
        "signature": _signature(fn),
        "args": [x.arg for x in all_args],
        "defaults": defaults,
        "annotations": {x.arg: ast.unparse(x.annotation) for x in all_args if x.annotation is not None},
        "return_annotation": _unparse(fn.returns),
        "docstring": ast.get_docstring(fn) or "",
        "decorators": _decorator_names(fn),
        "source": "".join(source_lines[start - 1:fn.end_lineno]).rstrip() + "\n",
        "imports": imports,
        "class_context": _class_context(cls) if cls else "",
    }


def extract_functions(root: Path) -> ExtractionResult:
    """Extract every non-trivial module-level function and method from non-test files."""
    root = Path(root)
    result = ExtractionResult()
    for rel in iter_python_files(root):
        result.files.append(rel)
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=rel)
        except (SyntaxError, ValueError) as exc:
            line = getattr(exc, "lineno", None)
            result.warnings.append(f"Skipped {rel}: syntax error{f' at line {line}' if line else ''}")
            continue
        result.trees[rel] = tree
        lines = text.splitlines(keepends=True)
        imports = _import_lines(tree, lines)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not is_trivial(node):
                    result.functions.append(_record(rel, node, lines, imports, None))
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not is_trivial(sub):
                        result.functions.append(_record(rel, sub, lines, imports, node))
    return result


def _iter_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                yield f.id, node.lineno
            elif isinstance(f, ast.Attribute):
                yield f.attr, node.lineno


def find_call_sites(root: Path, trees: dict[str, ast.Module]) -> dict[str, list[tuple[str, int]]]:
    """Map called name -> list of (file, line) across the given (non-test) module trees."""
    sites: dict[str, list[tuple[str, int]]] = {}
    for rel, tree in trees.items():
        for name, line in _iter_calls(tree):
            sites.setdefault(name, []).append((rel, line))
    return sites


def count_calls(func: dict, sites: dict[str, list[tuple[str, int]]]) -> int:
    """Number of call sites of ``func`` by name, excluding calls inside its own definition."""
    name = func["name"]
    if name == "__init__" and func.get("class_name"):
        name = func["class_name"]
    return len([
        (f, ln) for f, ln in sites.get(name, [])
        if not (f == func["file"] and func["line_start"] <= ln <= func["line_end"])
    ])


def example_call_sites(func: dict, root: Path, sites: dict[str, list[tuple[str, int]]], limit: int = 2) -> list[str]:
    """Up to ``limit`` source lines that call ``func`` (for the generation prompt)."""
    name = func["class_name"] if func["name"] == "__init__" and func.get("class_name") else func["name"]
    out: list[str] = []
    for f, ln in sites.get(name, []):
        if f == func["file"] and func["line_start"] <= ln <= func["line_end"]:
            continue
        try:
            line = (Path(root) / f).read_text(encoding="utf-8", errors="replace").splitlines()[ln - 1].strip()
        except (OSError, IndexError):
            continue
        out.append(f"{f}:{ln}: {line}")
        if len(out) >= limit:
            break
    return out
