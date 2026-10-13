from pathlib import Path

from app.analyzer import (
    count_calls,
    example_call_sites,
    extract_functions,
    find_call_sites,
    is_test_file,
    iter_python_files,
    module_name_for,
)

EXPECTED_IDS = {
    "billing.py::calculate_discount",
    "billing.py::apply_coupon",
    "billing.py::tax_for",
    "cart.py::Cart.add_item",
    "cart.py::Cart.remove_item",
    "cart.py::Cart.cart_total",
    "checkout.py::order_reference",
    "checkout.py::checkout",
    "checkout.py::quick_quote",
    "utils.py::slugify",
    "utils.py::is_valid_email",
    "utils.py::chunk_list",
}


def by_id(result):
    return {f["id"]: f for f in result.functions}


def test_sample_repo_functions(sample_repo):
    res = extract_functions(sample_repo)
    funcs = by_id(res)
    assert set(funcs) == EXPECTED_IDS  # Cart.__init__ is plain attribute assignment -> skipped
    assert res.warnings == []
    assert "tests/test_cart.py" not in res.files


def test_line_ranges_docstrings_signatures(sample_repo):
    funcs = by_id(extract_functions(sample_repo))
    lines = (sample_repo / "billing.py").read_text().splitlines()
    ac = funcs["billing.py::apply_coupon"]
    assert lines[ac["line_start"] - 1].startswith("def apply_coupon(")
    assert lines[ac["line_end"] - 1].strip() == "return total"
    assert "at least the minimum amount" in ac["docstring"]
    assert ac["signature"] == "apply_coupon(total, coupon)"
    assert ac["source"].startswith("def apply_coupon(total, coupon):")
    m = funcs["cart.py::Cart.remove_item"]
    assert m["is_method"] and m["class_name"] == "Cart" and m["qualname"] == "Cart.remove_item"
    assert m["defaults"] == {"quantity": "None"}
    assert "def __init__(self): ..." in m["class_context"]
    assert any("from billing import" in i for i in m["imports"])


def test_trivial_and_syntax_error(tmp_path: Path):
    (tmp_path / "mod.py").write_text(
        "import abc\n\n"
        "def stub():\n    pass\n\n"
        "def dots():\n    '''doc'''\n    ...\n\n"
        "def real(x: int = 1) -> int:\n    return x + 1\n\n"
        "class A(abc.ABC):\n"
        "    def __init__(self, v):\n        self.v = v\n\n"
        "    def __repr__(self):\n        return f'A({self.v})'\n\n"
        "    @abc.abstractmethod\n    def run(self):\n        raise NotImplementedError\n\n"
        "    async def go(self, *args, k=2, **kw):\n        return self.v * k\n\n"
        "class B:\n    def __init__(self, v):\n        if v < 0:\n            raise ValueError\n        self.v = v\n"
    )
    (tmp_path / "broken.py").write_text("def oops(:\n")
    res = extract_functions(tmp_path)
    ids = set(by_id(res))
    assert ids == {"mod.py::real", "mod.py::A.go", "mod.py::B.__init__"}
    assert by_id(res)["mod.py::real"]["signature"] == "real(x: int = 1) -> int"
    assert by_id(res)["mod.py::A.go"]["signature"] == "go(self, *args, k=2, **kw)"
    assert by_id(res)["mod.py::A.go"]["is_async"]
    assert any("broken.py" in w for w in res.warnings)


def test_file_filters(tmp_path: Path):
    for rel in ["a.py", "tests/test_a.py", "pkg/b_test.py", "conftest.py", "test_x.py",
                ".venv/lib/x.py", "node_modules/y.py", "src/pkg/core.py"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x = 1\n")
    assert iter_python_files(tmp_path) == ["a.py", "src/pkg/core.py"]
    assert is_test_file("tests/helpers.py") and not is_test_file("testing_utils.py")
    assert module_name_for("src/pkg/core.py") == "pkg.core"
    assert module_name_for("pkg/__init__.py") == "pkg"
    assert module_name_for("billing.py") == "billing"


def test_call_counting(sample_repo):
    res = extract_functions(sample_repo)
    sites = find_call_sites(sample_repo, res.trees)
    funcs = by_id(res)
    assert count_calls(funcs["billing.py::apply_coupon"], sites) == 2
    assert count_calls(funcs["billing.py::calculate_discount"], sites) == 2
    assert count_calls(funcs["utils.py::chunk_list"], sites) == 0
    examples = example_call_sites(funcs["billing.py::apply_coupon"], sample_repo, sites)
    assert len(examples) == 2 and all("apply_coupon(" in e for e in examples)


def test_recursive_calls_excluded(tmp_path: Path):
    (tmp_path / "r.py").write_text("def fact(n):\n    return 1 if n <= 1 else n * fact(n - 1)\n\nprint(fact(3))\n")
    res = extract_functions(tmp_path)
    sites = find_call_sites(tmp_path, res.trees)
    assert count_calls(res.functions[0], sites) == 1
