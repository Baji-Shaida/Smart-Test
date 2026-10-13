import pytest

from cart import Cart


def test_add_item_new_and_existing():
    cart = Cart()
    cart.add_item("apple", 1.5, 2)
    cart.add_item("apple", 1.5, 1)
    assert cart.items["apple"] == (1.5, 3)


def test_add_item_rejects_bad_quantity():
    with pytest.raises(ValueError):
        Cart().add_item("apple", 1.0, 0)


def test_cart_total_without_discount():
    cart = Cart()
    cart.add_item("apple", 2.0, 3)
    assert cart.cart_total() == 6.0
