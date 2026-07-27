"""
The cart isn't one of the three Excel files -- it's short-lived, per-visitor
state, so it lives in the signed session cookie instead: a plain dict of
{item_id (str): quantity (int)}. It only becomes durable once an order is
placed, at which point it's written into the customer's TransactionHistory
and the cart is cleared.
"""

from flask import session
from excel_helpers import GROCERIES_FILE, get_row_by_id


def get_cart():
    """The current visitor's cart dict, creating an empty one if needed."""
    return session.setdefault("cart", {})


def save_cart(cart):
    session["cart"] = cart
    session.modified = True


def cart_items_detailed():
    """Join the cart against the live groceries sheet so quantities,
    prices and stock are always current. Returns (items, total)."""
    cart = get_cart()
    items = []
    total = 0.0
    for item_id, qty in cart.items():
        grocery = get_row_by_id(GROCERIES_FILE, "ItemID", item_id)
        if not grocery:
            continue  # item was deleted from inventory since it was added
        price = float(grocery["PricePerUnit"])
        subtotal = price * qty
        total += subtotal
        items.append({
            "item_id": str(item_id),
            "name": grocery["Name"],
            "unit": grocery["Unit"],
            "price": price,
            "quantity": qty,
            "subtotal": subtotal,
            "in_stock": int(grocery["QuantityInStock"]),
            "image_url": grocery.get("ImageURL") or "",
        })
    items.sort(key=lambda i: i["name"].lower())
    return items, total
