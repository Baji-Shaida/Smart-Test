import sys

import pytest

from app.analyzer import example_call_sites, extract_functions, find_call_sites
from app.generator.llm import LLMClient
from app.generator.mock_llm import MockLLMClient
from app.validator import (
    FunctionContext,
    function_status,
    keep_only_tests,
    parse_verdict,
    process_function,
    run_pytest,
    static_check,
)
from app.validator.classify import observe

FN = {"module": "billing", "name": "apply_coupon", "qualname": "apply_coupon", "is_method": False}
METHOD = {"module": "cart", "name": "remove_item", "qualname": "Cart.remove_item", "is_method": True,
          "class_name": "Cart"}


@pytest.mark.parametrize("code,check", [
    ("def test_x(:\n  pass", "C1"),
    ("from billing import apply_coupon\n\ndef test_x():\n    assert 1 == 1\n", "C2"),
    ("from other import apply_coupon\n\ndef test_x():\n    assert apply_coupon(1, {}) == 1\n", "C2"),
    ("from billing import apply_coupon\n\ndef test_x():\n    apply_coupon(1, {})\n    assert True\n", "C3"),
    ("from billing import apply_coupon\n\ndef helper():\n    return apply_coupon(1, {})\n", "C2"),
])
def test_static_check_failures(code, check):
    res = static_check(code, FN)
    assert not res.ok and res.check == check


def test_static_check_passes():
    assert static_check("from billing import apply_coupon\n\ndef test_a():\n    r = apply_coupon(1, {})\n"
                        "    assert r == 1\n", FN).ok
    assert static_check("import pytest\nfrom billing import apply_coupon as ac\n\ndef test_a():\n"
                        "    with pytest.raises(KeyError):\n        ac(1, {})\n", FN).ok
    assert static_check("import billing\n\ndef test_a():\n    assert billing.apply_coupon(1, {}) == 1\n", FN).ok
    assert static_check("from cart import Cart\n\ndef test_a():\n    c = Cart()\n    c.items['a'] = (1, 1)\n"
                        "    c.remove_item('a')\n    assert c.items == {}\n", METHOD).ok
    assert not static_check("from cart import Cart\n\ndef test_a():\n    assert Cart().cart_total() == 0\n",
                            METHOD).ok


def test_keep_only_tests():
    code = "import x\n\n\ndef test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n\n\ndef helper():\n    pass\n"
    out = keep_only_tests(code, {"test_b"})
    assert "test_a" not in out and "test_b" in out and "helper" in out


def test_parse_verdict_defensive():
    assert parse_verdict('{"verdict": "likely_bug", "reason": "off by one"}')["verdict"] == "likely_bug"
    assert parse_verdict('Sure!\n```json\n{"verdict": "test_wrong", "reason": "x"}\n```')["verdict"] == "test_wrong"
    assert parse_verdict("I think it's a bug")["verdict"] == "unclear"
    assert parse_verdict('{"verdict": "maybe"}')["verdict"] == "unclear"


def test_function_status_precedence():
    assert function_status(["accepted", "possible_bug", "needs_review"]) == "possible_bug"
    assert function_status(["accepted", "needs_review", "rejected"]) == "needs_review"
    assert function_status(["accepted", "rejected"]) == "accepted"
    assert function_status(["rejected", "rejected"]) == "rejected"


def _write_module(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.py").write_text("def f(x):\n    return 10 / x\n")
    return repo


def test_runner_and_observations(tmp_path):
    repo = _write_module(tmp_path)
    t = tmp_path / "gen" / "test_m__f.py"
    t.parent.mkdir()
    t.write_text(
        "import pytest\nfrom m import f\n"
        "def test_pass():\n    assert f(2) == 5\n"
        "def test_assert():\n    assert f(5) == 3\n"
        "def test_target_raises():\n    assert f(0) == 1\n"
        "def test_arity():\n    assert f(1, 2) == 1\n"
        "def test_noraise():\n    with pytest.raises(ValueError):\n        f(1)\n"
        "def test_name():\n    assert g(1) == 1\n"
        "def test_fixture(nope):\n    assert f(1)\n"
    )
    run = run_pytest(t, repo, tmp_path, sys.executable, 30)
    obs = {n: observe(c, t.name, "f") for n, c in run.cases.items()}
    assert obs["test_pass"].kind == "passed"
    assert obs["test_assert"].kind == "failure"
    assert (obs["test_assert"].expected, obs["test_assert"].actual) == ("3", "2.0")
    assert obs["test_target_raises"].kind == "failure" and "ZeroDivisionError" in obs["test_target_raises"].actual
    assert obs["test_arity"].kind == "invalid" and "call site" in obs["test_arity"].reason
    assert obs["test_noraise"].kind == "failure" and obs["test_noraise"].expected == "raises ValueError"
    assert obs["test_name"].kind == "invalid"
    assert obs["test_fixture"].kind == "invalid" and "fixture" in obs["test_fixture"].reason


def test_runner_collection_error(tmp_path):
    repo = _write_module(tmp_path)
    t = tmp_path / "test_m__f.py"
    t.write_text("from m import nothing_here\n\ndef test_x():\n    assert nothing_here() == 1\n")
    run = run_pytest(t, repo, tmp_path, sys.executable, 30)
    assert run.collection_error and "ImportError" in run.collection_error


class ScriptedLLM(LLMClient):
    """Returns a fixed code block for generation and a fixed verdict for verification."""

    def __init__(self, code, verdict='{"verdict": "unclear", "reason": "?"}'):
        self.code, self.verdict, self.calls = code, verdict, 0

    def generate(self, prompt):
        self.calls += 1
        if prompt.startswith("A generated test failed."):
            return self.verdict
        return f"```python\n{self.code}\n```"


def _ctx(tmp_path, repo, client, timeout=30):
    return FunctionContext(repo, tmp_path, tmp_path / "generated_tests", sys.executable, timeout, client)


def _fn(repo):
    return extract_functions(repo).functions[0]


def test_timeout_becomes_needs_review(tmp_path):
    repo = _write_module(tmp_path)
    code = "import time\nfrom m import f\n\ndef test_f_slow():\n    time.sleep(30)\n    assert f(2) == 5\n"
    out = process_function(_fn(repo), [], _ctx(tmp_path, repo, ScriptedLLM(code), timeout=2))
    assert out.status == "needs_review"
    assert out.tests[0]["reason"].startswith("Timed out")


def test_flaky_becomes_needs_review(tmp_path):
    repo = _write_module(tmp_path)
    marker = tmp_path / "flip"
    code = (f"import os\nfrom m import f\n\nMARK = {str(marker)!r}\n\n"
            "def test_f_flaky():\n    first = not os.path.exists(MARK)\n    open(MARK, 'w').close()\n"
            "    assert f(2) == (4 if first else 5)\n")
    out = process_function(_fn(repo), [], _ctx(tmp_path, repo, ScriptedLLM(code)))
    assert out.status == "needs_review"
    assert "Flaky" in out.tests[0]["reason"]


def test_invalid_test_is_retried_then_rejected(tmp_path):
    repo = _write_module(tmp_path)
    client = ScriptedLLM("from m import f\n\ndef test_f_args():\n    assert f(1, 2, 3) == 1\n")
    out = process_function(_fn(repo), [], _ctx(tmp_path, repo, client))
    assert out.status == "rejected" and out.attempts == 3 and client.calls == 3
    assert "call site" in out.tests[0]["reason"]


def test_test_wrong_twice_is_rejected_never_bug(tmp_path):
    repo = _write_module(tmp_path)
    client = ScriptedLLM("from m import f\n\ndef test_f_value():\n    assert f(2) == 7\n",
                         '{"verdict": "test_wrong", "reason": "10/2 is 5"}')
    out = process_function(_fn(repo), [], _ctx(tmp_path, repo, client))
    assert out.status == "rejected"
    assert all(t["status"] != "possible_bug" for t in out.tests)


def test_sample_repo_all_classifications(sample_repo, tmp_path):
    res = extract_functions(sample_repo)
    sites = find_call_sites(sample_repo, res.trees)
    ctx = _ctx(tmp_path, sample_repo, MockLLMClient())
    statuses = {}
    outcomes = {}
    for fn in res.functions:
        if fn["id"] in {"billing.py::tax_for", "cart.py::Cart.add_item", "utils.py::slugify"}:
            continue
        outcomes[fn["id"]] = process_function(fn, example_call_sites(fn, sample_repo, sites), ctx)
        statuses[fn["id"]] = outcomes[fn["id"]].status
    assert statuses["billing.py::calculate_discount"] == "accepted"
    assert statuses["billing.py::apply_coupon"] == "possible_bug"
    assert statuses["utils.py::chunk_list"] == "possible_bug"
    assert statuses["cart.py::Cart.remove_item"] == "rejected"
    assert statuses["checkout.py::order_reference"] == "accepted"
    assert outcomes["checkout.py::order_reference"].attempts == 2
    assert statuses["checkout.py::checkout"] == "accepted"
    assert statuses["checkout.py::quick_quote"] == "needs_review"
    bug = next(t for t in outcomes["billing.py::apply_coupon"].tests if t["status"] == "possible_bug")
    assert bug["name"] == "test_apply_coupon_at_minimum_boundary"
    assert (bug["expected"], bug["actual"]) == ("45.0", "50")
    assert bug["verdict"]["verdict"] == "likely_bug" and bug["traceback"]
    assert (tmp_path / "generated_tests" / "test_billing__apply_coupon.py").is_file()
