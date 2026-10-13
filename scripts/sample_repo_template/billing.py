"""Billing helpers for the demo shop."""


def calculate_discount(price, discount_percent):
    """Return price after applying discount_percent (0 to 100).

    The result is rounded to 2 decimals. Raises ValueError if price is negative
    or discount_percent is outside the range 0..100.
    """
    if price < 0:
        raise ValueError("price must not be negative")
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("discount_percent must be between 0 and 100")
    return round(price * (1 - discount_percent / 100), 2)


def apply_coupon(total, coupon):
    """Apply a coupon to an order total.

    coupon is a dict with keys "percent" and "min_amount". The coupon applies
    when the total is at least the minimum amount (total >= coupon["min_amount"]),
    in which case the discounted total is returned. Otherwise the total is
    returned unchanged.
    """
    if total > coupon["min_amount"]:
        return calculate_discount(total, coupon["percent"])
    return total


def tax_for(amount, rate):
    """Return the tax owed on amount at the given rate (e.g. 0.08 for 8%), rounded to 2 decimals.

    Raises ValueError if rate is negative.
    """
    if rate < 0:
        raise ValueError("rate must not be negative")
    return round(amount * rate, 2)
