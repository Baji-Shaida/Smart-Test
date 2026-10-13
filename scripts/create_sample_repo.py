#!/usr/bin/env python3
"""Create the SmartTest demo repository (a tiny Python shop) with a dated git history.

The committed template lives in scripts/sample_repo_template/. This script copies it into
``sample_repo/`` (or --dest) and builds it up over at least 8 commits with different dates
(GIT_AUTHOR_DATE / GIT_COMMITTER_DATE), so that git blame recency differs per function.

Usage:
    python scripts/create_sample_repo.py                # -> ./sample_repo
    python scripts/create_sample_repo.py --dest /tmp/x --force
    python scripts/create_sample_repo.py --no-git        # plain copy, no history
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "sample_repo_template"
DEFAULT_DEST = Path(__file__).resolve().parent.parent / "sample_repo"

# (days_ago, message, {file: set of top-level names / "Class.method" to include, or None for whole file})
# Each commit writes the listed files with only the listed definitions, so git blame dates differ.
HISTORY: list[tuple[int, str, dict[str, set[str] | None]]] = [
    (180, "Initial commit: project skeleton and slugify", {
        "README.md": None, "requirements.txt": None, "utils.py": {"slugify"},
    }),
    (150, "Add chunk_list helper", {"utils.py": {"slugify", "chunk_list"}}),
    (120, "Add tax calculation", {"billing.py": {"tax_for"}}),
    (95, "Add Cart with add_item", {"cart.py": {"Cart", "Cart.__init__", "Cart.add_item"}}),
    (80, "Add tests for tax_for and Cart.add_item", {
        "tests/test_billing.py": None,
        "tests/test_cart.py": {"pytest", "Cart", "test_add_item_new_and_existing", "test_add_item_rejects_bad_quantity"},
    }),
    (60, "Add Cart.remove_item", {"cart.py": {"Cart", "Cart.__init__", "Cart.add_item", "Cart.remove_item"}}),
    (40, "Add email validation", {"utils.py": None}),
    (21, "Add calculate_discount and Cart.cart_total", {
        "billing.py": {"calculate_discount", "tax_for"},
        "cart.py": None,
        "tests/test_cart.py": None,
    }),
    (9, "Add checkout flow and order references", {"checkout.py": {"order_reference", "checkout"}}),
    (2, "Add coupons: apply_coupon and quick_quote", {"billing.py": None, "checkout.py": None}),
]


def partial_source(source: str, include: set[str] | None) -> str:
    """Return ``source`` keeping imports/constants and only the definitions named in ``include``."""
    if include is None:
        return source
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    drop: set[int] = set()

    def node_range(node: ast.AST) -> range:
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        return range(start, node.end_lineno + 1)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name not in include:
                drop.update(node_range(node))
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if f"{node.name}.{sub.name}" not in include:
                            drop.update(node_range(sub))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = {a.asname or a.name for a in node.names}
            if include and not names & include and any(n.startswith("test_") for n in include):
                drop.update(node_range(node))
    kept = "".join(line for i, line in enumerate(lines, start=1) if i not in drop)
    while "\n\n\n\n" in kept:
        kept = kept.replace("\n\n\n\n", "\n\n\n")
    return kept.rstrip() + "\n"


def run_git(dest: Path, *args: str, date: datetime | None = None) -> None:
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Demo Developer", "GIT_AUTHOR_EMAIL": "dev@example.com",
        "GIT_COMMITTER_NAME": "Demo Developer", "GIT_COMMITTER_EMAIL": "dev@example.com",
    })
    if date is not None:
        stamp = date.strftime("%Y-%m-%dT%H:%M:%S%z")
        env["GIT_AUTHOR_DATE"] = stamp
        env["GIT_COMMITTER_DATE"] = stamp
    subprocess.run(["git", *args], cwd=dest, env=env, check=True, capture_output=True, text=True)


def create_sample_repo(dest: Path = DEFAULT_DEST, force: bool = False, with_git: bool = True,
                       now: datetime | None = None) -> Path:
    dest = Path(dest).resolve()
    if dest.exists():
        if not force:
            raise SystemExit(f"{dest} already exists (use --force to replace it)")
        shutil.rmtree(dest)
    if not with_git:
        shutil.copytree(TEMPLATE, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return dest

    dest.mkdir(parents=True)
    now = now or datetime.now(timezone.utc)
    run_git(dest, "init", "-q")
    run_git(dest, "checkout", "-q", "-b", "main")
    for days_ago, message, files in HISTORY:
        for rel, include in files.items():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(partial_source((TEMPLATE / rel).read_text(), include))
        run_git(dest, "add", "-A")
        run_git(dest, "commit", "-q", "-m", message, date=now - timedelta(days=days_ago, hours=3))
    # Sanity check: the final tree must equal the template.
    for src in TEMPLATE.rglob("*"):
        if src.is_file() and "__pycache__" not in src.parts:
            rel = src.relative_to(TEMPLATE)
            if (dest / rel).read_text() != src.read_text():
                (dest / rel).write_text(src.read_text())
                run_git(dest, "add", "-A")
                run_git(dest, "commit", "-q", "-m", f"Sync {rel}", date=now - timedelta(days=1))
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", default=str(DEFAULT_DEST), help="output folder (default: ./sample_repo)")
    parser.add_argument("--force", action="store_true", help="replace the folder if it exists")
    parser.add_argument("--no-git", action="store_true", help="copy files without creating git history")
    parser.add_argument("--zip", action="store_true", help="also write <dest>.zip for uploading in the UI")
    args = parser.parse_args(argv)
    dest = create_sample_repo(Path(args.dest), force=args.force, with_git=not args.no_git)
    print(f"Sample repository created at {dest}")
    if args.zip:
        archive = shutil.make_archive(str(dest), "zip", root_dir=dest.parent, base_dir=dest.name)
        print(f"Zip archive written to {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
