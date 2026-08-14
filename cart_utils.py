from flask import session
from google_sheets_helpers import GROCERIES_FILE, get_all_rows

def get_cart():
    return session.setdefault("cart", {})

def save_cart(cart):
    session["cart"] = cart
    session.modified = True

def cart_items_detailed():
    cart = get_cart()
    items = []
    total = 0.0
    # One read for the whole sheet instead of one per cart line - avoids
    # hammering the Sheets API quota as the cart grows.
    groceries_by_id = {str(g["ItemID"]): g for g in get_all_rows(GROCERIES_FILE)}
    for item_id, qty in cart.items():
        grocery = groceries_by_id.get(str(item_id))
        if not grocery:
            continue
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
