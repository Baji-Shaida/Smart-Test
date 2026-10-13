"""Deterministic offline LLM used by automated tests, demos and machines without a GPU.

It recognises the prompt type (generation, retry, bug verification) and the function under test,
and returns canned pytest code for the sample repository (scripts/sample_repo_template). The
canned answers are designed to exercise every path of the pipeline:

* calculate_discount, tax_for, slugify, is_valid_email, Cart.add_item, Cart.cart_total -> ACCEPTED
* apply_coupon   -> boundary test fails, verification says likely_bug -> POSSIBLE BUG FOUND
* chunk_list     -> partial-chunk test fails, likely_bug -> POSSIBLE BUG FOUND (second, subtle bug)
* Cart.remove_item -> always ``assert True`` -> REJECTED (trivial test, after 2 retries)
* order_reference -> first answer has a syntax error, the retry is valid -> ACCEPTED (2 attempts)
* checkout       -> first answer has a wrong expected value, verification says test_wrong,
                    regenerated answer passes -> ACCEPTED
* quick_quote    -> boundary failure caused by a dependency, verdict unclear -> NEEDS REVIEW

Unknown functions get a smoke test that does not call the target, so they are REJECTED; use
Ollama for real projects.
"""
from __future__ import annotations

import json
import re

from .llm import LLMClient

_FUNC_RE = re.compile(r"FUNCTION UNDER TEST:\s*```python\s*\n(?:\s*@.*\n)*\s*(?:async\s+)?def\s+(\w+)")
_VERIFY_FUNC_RE = re.compile(r"FUNCTION:\s*```python\s*\n(?:\s*@.*\n)*\s*(?:async\s+)?def\s+(\w+)")
_IMPORT_RE = re.compile(r"IMPORT STATEMENT TO USE:\s*(.+)")


def _block(code: str) -> str:
    return f"Here are the tests.\n\n```python\n{code.strip()}\n```\n"


GOOD: dict[str, str] = {
    "calculate_discount": '''
import pytest
from billing import calculate_discount


def test_calculate_discount_basic():
    assert calculate_discount(100, 10) == 90.0


def test_calculate_discount_zero_percent():
    assert calculate_discount(80, 0) == 80.0


def test_calculate_discount_full_discount():
    assert calculate_discount(50, 100) == 0.0


def test_calculate_discount_rounds_to_cents():
    assert calculate_discount(19.99, 15) == 16.99


def test_calculate_discount_invalid_percent():
    with pytest.raises(ValueError):
        calculate_discount(100, 150)


def test_calculate_discount_negative_price():
    with pytest.raises(ValueError):
        calculate_discount(-1, 10)
''',
    "apply_coupon": '''
from billing import apply_coupon

COUPON = {"percent": 10, "min_amount": 50}


def test_apply_coupon_above_minimum():
    assert apply_coupon(100, COUPON) == 90.0


def test_apply_coupon_below_minimum_unchanged():
    assert apply_coupon(40, COUPON) == 40


def test_apply_coupon_at_minimum_boundary():
    # Docstring: the coupon applies when the total is at least the minimum amount.
    assert apply_coupon(50, COUPON) == 45.0


def test_apply_coupon_zero_total():
    assert apply_coupon(0, COUPON) == 0
''',
    "tax_for": '''
import pytest
from billing import tax_for


def test_tax_for_basic():
    assert tax_for(100, 0.08) == 8.0


def test_tax_for_zero_amount():
    assert tax_for(0, 0.2) == 0.0


def test_tax_for_rounding():
    assert tax_for(19.99, 0.07) == 1.4


def test_tax_for_negative_rate():
    with pytest.raises(ValueError):
        tax_for(10, -0.01)
''',
    "add_item": '''
import pytest
from cart import Cart


def test_add_item_new():
    cart = Cart()
    cart.add_item("pen", 2.5)
    assert cart.items == {"pen": (2.5, 1)}


def test_add_item_existing_increases_quantity():
    cart = Cart()
    cart.add_item("pen", 2.5, 2)
    cart.add_item("pen", 2.5, 3)
    assert cart.items["pen"] == (2.5, 5)


def test_add_item_negative_price():
    with pytest.raises(ValueError):
        Cart().add_item("pen", -1)
''',
    "cart_total": '''
from cart import Cart


def test_cart_total_empty():
    assert Cart().cart_total() == 0


def test_cart_total_with_discount():
    cart = Cart()
    cart.add_item("book", 50.0, 2)
    assert cart.cart_total(discount_percent=10) == 90.0


def test_cart_total_with_discount_and_tax():
    cart = Cart()
    cart.add_item("book", 50.0, 2)
    assert cart.cart_total(discount_percent=10, tax_rate=0.1) == 99.0
''',
    "slugify": '''
from utils import slugify


def test_slugify_basic():
    assert slugify("Hello, World!") == "hello-world"


def test_slugify_collapses_separators():
    assert slugify("  Many   spaces -- here ") == "many-spaces-here"


def test_slugify_empty():
    assert slugify("") == ""
''',
    "is_valid_email": '''
from utils import is_valid_email


def test_is_valid_email_valid():
    assert is_valid_email("jane.doe@example.org") is True


def test_is_valid_email_missing_domain():
    assert is_valid_email("jane@") is False


def test_is_valid_email_not_a_string():
    assert is_valid_email(42) is False
''',
    "chunk_list": '''
import pytest
from utils import chunk_list


def test_chunk_list_even_split():
    assert chunk_list([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_chunk_list_last_chunk_shorter():
    # Docstring: the last chunk may be shorter.
    assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunk_list_empty():
    assert chunk_list([], 3) == []


def test_chunk_list_invalid_size():
    with pytest.raises(ValueError):
        chunk_list([1], 0)
''',
    "order_reference": '''
from checkout import order_reference


def test_order_reference_basic():
    assert order_reference("Jane Doe", 42) == "jane-doe-0042"


def test_order_reference_strips_punctuation():
    assert order_reference("O'Brien, Pat!", 7) == "o-brien-pat-0007"


def test_order_reference_large_number():
    assert order_reference("Ann", 12345) == "ann-12345"
''',
    "checkout": '''
import pytest
from cart import Cart
from checkout import checkout


def _cart():
    cart = Cart()
    cart.add_item("book", 20.0, 2)
    return cart


def test_checkout_without_coupon():
    assert checkout(_cart(), "jane@example.com") == {"subtotal": 40.0, "tax": 3.2, "total": 43.2}


def test_checkout_with_coupon():
    result = checkout(_cart(), "jane@example.com", coupon={"percent": 10, "min_amount": 30}, tax_rate=0.1)
    assert result == {"subtotal": 36.0, "tax": 3.6, "total": 39.6}


def test_checkout_invalid_email():
    with pytest.raises(ValueError):
        checkout(_cart(), "not-an-email")


def test_checkout_empty_cart():
    with pytest.raises(ValueError):
        checkout(Cart(), "jane@example.com")
''',
    "quick_quote": '''
from cart import Cart
from checkout import quick_quote


def _cart(price):
    cart = Cart()
    cart.add_item("item", price, 1)
    return cart


def test_quick_quote_no_coupon():
    assert quick_quote(_cart(80.0)) == 80.0


def test_quick_quote_coupon_applied():
    assert quick_quote(_cart(100.0), {"percent": 20, "min_amount": 50}) == 80.0


def test_quick_quote_coupon_at_minimum():
    assert quick_quote(_cart(50.0), {"percent": 20, "min_amount": 50}) == 40.0
''',
}

FIRST_ATTEMPT: dict[str, str] = {
    # deliberately trivial -> REJECTED
    "remove_item": '''
from cart import Cart


def test_remove_item_works():
    cart = Cart()
    cart.add_item("apple", 1.0, 2)
    cart.remove_item("apple")
    assert True
''',
    # syntax error (missing colon) -> fixed on retry
    "order_reference": '''
from checkout import order_reference


def test_order_reference_basic()
    assert order_reference("Jane Doe", 42) == "jane-doe-0042"
''',
    # wrong expected tax (assumes 10% instead of the default 8%) -> verification says test_wrong
    "checkout": '''
import pytest
from cart import Cart
from checkout import checkout


def _cart():
    cart = Cart()
    cart.add_item("book", 20.0, 2)
    return cart


def test_checkout_without_coupon():
    result = checkout(_cart(), "jane@example.com")
    assert result["tax"] == 4.0


def test_checkout_invalid_email():
    with pytest.raises(ValueError):
        checkout(_cart(), "not-an-email")


def test_checkout_empty_cart():
    with pytest.raises(ValueError):
        checkout(Cart(), "jane@example.com")
''',
}

ALWAYS_BAD = {"remove_item"}

VERDICTS: dict[str, dict] = {
    "apply_coupon": {
        "verdict": "likely_bug",
        "reason": "The docstring says the coupon applies when the total is at least min_amount, "
                  "but the code uses > instead of >=, so a total equal to min_amount gets no discount.",
    },
    "chunk_list": {
        "verdict": "likely_bug",
        "reason": "The docstring says the last chunk may be shorter, but the range stops before the "
                  "remainder, so the final partial chunk is silently dropped.",
    },
    "checkout": {
        "verdict": "test_wrong",
        "reason": "The default tax_rate is 0.08, so tax on 40.0 is 3.2; the test assumed a 10% rate.",
    },
    "quick_quote": {
        "verdict": "unclear",
        "reason": "The failure comes from apply_coupon, which quick_quote only delegates to; "
                  "a human should decide which function is at fault.",
    },
}


class MockLLMClient(LLMClient):
    name = "mock"
    model = "mock"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        if prompt.startswith("A generated test failed."):
            m = _VERIFY_FUNC_RE.search(prompt)
            name = m.group(1) if m else ""
            verdict = VERDICTS.get(name, {"verdict": "unclear", "reason": "Mock LLM has no opinion."})
            return json.dumps(verdict)
        m = _FUNC_RE.search(prompt)
        name = m.group(1) if m else ""
        is_retry = "Your previous test code was rejected." in prompt
        if name in ALWAYS_BAD:
            code = FIRST_ATTEMPT[name]
            if is_retry:
                code = code.replace("assert True", "assert 1 == 1")
            return _block(code)
        if not is_retry and name in FIRST_ATTEMPT:
            return _block(FIRST_ATTEMPT[name])
        if name in GOOD:
            return _block(GOOD[name])
        return _block(self._fallback(prompt, name or "target"))

    @staticmethod
    def _fallback(prompt: str, name: str) -> str:
        m = _IMPORT_RE.search(prompt)
        imp = m.group(1).strip() if m else f"# import {name}"
        target = imp.split(" import ")[-1].strip() if " import " in imp else name
        return f"{imp}\n\n\ndef test_{name.strip('_')}_exists():\n    assert callable({target})\n"
