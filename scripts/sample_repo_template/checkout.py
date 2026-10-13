"""Checkout flow that ties the cart and billing together."""
from billing import apply_coupon, tax_for
from utils import is_valid_email, slugify


def order_reference(customer_name, order_number):
    """Return a readable order reference such as "jane-doe-0042"."""
    return f"{slugify(customer_name)}-{order_number:04d}"


def checkout(cart, email, coupon=None, tax_rate=0.08):
    """Compute the final amount for a cart.

    Applies the coupon (if any) to the cart subtotal, then adds tax at tax_rate.
    Returns a dict with "subtotal", "tax" and "total". Raises ValueError for an
    invalid email address or an empty cart.
    """
    if not is_valid_email(email):
        raise ValueError("invalid email")
    if not cart.items:
        raise ValueError("cart is empty")
    subtotal = cart.cart_total()
    if coupon:
        subtotal = apply_coupon(subtotal, coupon)
    tax = tax_for(subtotal, tax_rate)
    return {"subtotal": subtotal, "tax": tax, "total": round(subtotal + tax, 2)}


def quick_quote(cart, coupon=None):
    """Return the cart total after an optional coupon, without tax."""
    total = cart.cart_total()
    if coupon:
        total = apply_coupon(total, coupon)
    return total
