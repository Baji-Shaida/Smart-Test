import ast

import httpx
import pytest

from app.analyzer import example_call_sites, extract_functions, find_call_sites
from app.generator import (
    LLMError,
    OllamaClient,
    TestGenerator,
    build_generation_prompt,
    build_verification_prompt,
    extract_code,
    generated_test_filename,
    get_llm_client,
    import_statement,
)
from app.generator.mock_llm import MockLLMClient


def syntax_check(code):
    try:
        ast.parse(code)
        return None
    except SyntaxError as exc:
        return f"SyntaxError: {exc.msg} at line {exc.lineno}"


@pytest.fixture()
def funcs(sample_repo):
    res = extract_functions(sample_repo)
    return {f["id"]: f for f in res.functions}, find_call_sites(sample_repo, res.trees)


def test_import_statements():
    assert import_statement({"module": "billing", "name": "f", "is_method": False}) == "from billing import f"
    assert import_statement({"module": "pkg.cart", "name": "m", "is_method": True, "class_name": "Cart"}) \
        == "from pkg.cart import Cart"
    name = generated_test_filename({"module": "pkg.cart", "qualname": "Cart.add_item"})
    assert name == "test_pkg_cart__Cart_add_item.py"


def test_src_layout_import(tmp_path):
    (tmp_path / "src" / "shop").mkdir(parents=True)
    (tmp_path / "src" / "shop" / "core.py").write_text("def f(x):\n    return x * 2\n")
    fn = extract_functions(tmp_path).functions[0]
    assert import_statement(fn) == "from shop.core import f"


def test_generation_prompt_contents(sample_repo, funcs):
    by_id, sites = funcs
    fn = by_id["cart.py::Cart.remove_item"]
    prompt = build_generation_prompt(fn, example_call_sites(fn, sample_repo, sites))
    assert "IMPORT STATEMENT TO USE: from cart import Cart" in prompt
    assert "class Cart:" in prompt and "def remove_item(self, name, quantity=None):" in prompt
    assert "EXAMPLE CALL SITES FROM THE CODEBASE:\nnone found" in prompt
    assert "test_remove_item_<scenario>" in prompt
    fn2 = by_id["billing.py::apply_coupon"]
    p2 = build_generation_prompt(fn2, example_call_sites(fn2, sample_repo, sites))
    assert "checkout.py:" in p2 and "at least the minimum amount" in p2


def test_extract_code_variants():
    assert extract_code("text\n```python\nx = 1\n```\nmore ```python\ny=2\n```") == "x = 1\n"
    assert extract_code("```\nz = 3\n```") == "z = 3\n"
    assert extract_code("```py\nunclosed = True\n") == "unclosed = True\n"
    assert extract_code("assert f() == 1") == "assert f() == 1\n"


def test_mock_returns_valid_code(funcs):
    by_id, _ = funcs
    gen = TestGenerator(MockLLMClient())
    res = gen.generate(by_id["billing.py::apply_coupon"], [], syntax_check)
    assert res.ok and res.attempts == 1
    assert "from billing import apply_coupon" in res.code
    assert "test_apply_coupon_at_minimum_boundary" in res.code


def test_retry_path_when_mock_returns_invalid_code(funcs):
    by_id, _ = funcs
    client = MockLLMClient()
    res = TestGenerator(client).generate(by_id["checkout.py::order_reference"], [], syntax_check)
    assert res.ok and res.attempts == 2
    assert len(client.calls) == 2
    assert "Your previous test code was rejected." in client.calls[1]
    assert "PROBLEM: SyntaxError" in client.calls[1]
    assert "FUNCTION UNDER TEST" in client.calls[1]  # original context kept for stateless LLMs
    assert res.history[0]["problem"].startswith("SyntaxError")


def test_retry_gives_up_after_two_retries(funcs):
    by_id, _ = funcs
    client = MockLLMClient()
    res = TestGenerator(client, max_retries=2).generate(
        by_id["cart.py::Cart.remove_item"], [],
        lambda code: "trivial test" if "assert True" in code or "1 == 1" in code else None,
    )
    assert not res.ok and res.attempts == 3 and len(client.calls) == 3


def test_mock_verification_json(funcs):
    by_id, _ = funcs
    client = MockLLMClient()
    import json
    prompt = build_verification_prompt(by_id["billing.py::apply_coupon"], "def test(): ...", "E assert 50 == 45.0")
    out = json.loads(client.generate(prompt))
    assert out["verdict"] == "likely_bug"


def test_get_llm_client_selection():
    assert isinstance(get_llm_client("mock"), MockLLMClient)
    c = get_llm_client("ollama", model="llama3.1:8b")
    assert isinstance(c, OllamaClient) and c.model == "llama3.1:8b"


def test_ollama_client_success(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(url=url, json=json, timeout=timeout)
        return httpx.Response(200, json={"response": "```python\nx = 1\n```"})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = OllamaClient(base_url="http://ollama:11434", model="qwen2.5-coder:7b", timeout=5).generate("hi")
    assert "x = 1" in out
    assert captured["url"] == "http://ollama:11434/api/generate"
    assert captured["json"]["model"] == "qwen2.5-coder:7b" and captured["json"]["stream"] is False


def test_ollama_client_unreachable():
    with pytest.raises(LLMError, match="unreachable"):
        OllamaClient(base_url="http://127.0.0.1:9", timeout=2).generate("hi")


def test_ollama_client_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(404, text="model not found"))
    with pytest.raises(LLMError, match="404"):
        OllamaClient(base_url="http://x", timeout=1).generate("hi")
