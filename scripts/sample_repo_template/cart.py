"""Shopping cart for the demo shop."""
from billing import calculate_discount, tax_for


class Cart:
    """A simple shopping cart that maps item names to (price, quantity)."""

    def __init__(self):
        self.items = {}

    def add_item(self, name, price, quantity=1):
        """Add quantity units of an item. Adding an existing item increases its quantity.

        Raises ValueError if quantity is not positive or price is negative.
        """
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price < 0:
            raise ValueError("price must not be negative")
        if name in self.items:
            old_price, old_qty = self.items[name]
            self.items[name] = (old_price, old_qty + quantity)
        else:
            self.items[name] = (price, quantity)

    def remove_item(self, name, quantity=None):
        """Remove an item. If quantity is given, only remove that many units.

        The item disappears when its quantity reaches zero. Raises KeyError if
        the item is not in the cart.
        """
        if name not in self.items:
            raise KeyError(name)
        price, qty = self.items[name]
        if quantity is None or quantity >= qty:
            del self.items[name]
        else:
            self.items[name] = (price, qty - quantity)

    def cart_total(self, discount_percent=0, tax_rate=0.0):
        """Return the cart total: subtotal, minus discount_percent, plus tax at tax_rate.

        The result is rounded to 2 decimals. An empty cart totals 0.
        """
        subtotal = sum(price * qty for price, qty in self.items.values())
        if discount_percent:
            subtotal = calculate_discount(subtotal, discount_percent)
        return round(subtotal + tax_for(subtotal, tax_rate), 2)
