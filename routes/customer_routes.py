"""Customer portal: registration, login, browsing, cart, checkout,
profile, and order history."""

from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash,
)
from werkzeug.security import generate_password_hash, check_password_hash

from excel_helpers import (
    CUSTOMERS_FILE, GROCERIES_FILE,
    get_all_rows, get_row_by_id, get_row_by_email,
    create_record, update_row,
    parse_transaction_history, serialize_transaction_history,
)
from decorators import customer_required
from cart_utils import get_cart, save_cart, cart_items_detailed

customer_bp = Blueprint("customer", __name__, url_prefix="/customer")

PAYMENT_METHODS = ["Cash on Delivery", "UPI", "Card"]


# ---------------------------------------------------------------------------
# Registration + login
# ---------------------------------------------------------------------------

@customer_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Name, email, and password are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif get_row_by_email(CUSTOMERS_FILE, email):
            flash("An account with that email already exists.", "error")
        else:
            create_record(CUSTOMERS_FILE, "CustomerID", {
                "Name": name,
                "Email": email,
                "Phone": phone,
                "PasswordHash": generate_password_hash(password),
                "TransactionHistory": "[]",
                "CreatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            flash("Account created. Please log in.", "success")
            return redirect(url_for("customer.login"))

    return render_template("customer/register.html")


@customer_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        customer = get_row_by_email(CUSTOMERS_FILE, email)
        if customer and check_password_hash(customer["PasswordHash"], password):
            session["customer_id"] = str(customer["CustomerID"])
            session["customer_name"] = customer["Name"]
            flash(f"Welcome back, {customer['Name']}.", "success")
            return redirect(url_for("customer.dashboard"))
        flash("That email and password do not match our records.", "error")
    return render_template("customer/login.html")


@customer_bp.route("/logout")
def logout():
    session.pop("customer_id", None)
    session.pop("customer_name", None)
    session.pop("cart", None)
    flash("Logged out.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Browsing
# ---------------------------------------------------------------------------

@customer_bp.route("/dashboard")
@customer_required
def dashboard():
    groceries = get_all_rows(GROCERIES_FILE)
    groceries.sort(key=lambda g: g["Name"].lower())
    cart = get_cart()
    return render_template("customer/dashboard.html", groceries=groceries, cart=cart)


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------

@customer_bp.route("/cart/add/<item_id>", methods=["POST"])
@customer_required
def cart_add(item_id):
    grocery = get_row_by_id(GROCERIES_FILE, "ItemID", item_id)
    if not grocery:
        flash("That item no longer exists.", "error")
        return redirect(request.referrer or url_for("customer.dashboard"))

    cart = get_cart()
    current_qty = cart.get(item_id, 0)
    if current_qty + 1 > int(grocery["QuantityInStock"]):
        flash(f'Only {grocery["QuantityInStock"]} {grocery["Unit"]} of {grocery["Name"]} in stock.', "error")
    else:
        cart[item_id] = current_qty + 1
        save_cart(cart)

    return redirect(request.referrer or url_for("customer.dashboard"))


@customer_bp.route("/cart/decrement/<item_id>", methods=["POST"])
@customer_required
def cart_decrement(item_id):
    cart = get_cart()
    if item_id in cart:
        cart[item_id] -= 1
        if cart[item_id] <= 0:
            del cart[item_id]
        save_cart(cart)
    return redirect(request.referrer or url_for("customer.dashboard"))


@customer_bp.route("/cart/remove/<item_id>", methods=["POST"])
@customer_required
def cart_remove(item_id):
    cart = get_cart()
    cart.pop(item_id, None)
    save_cart(cart)
    flash("Item removed from cart.", "success")
    return redirect(url_for("customer.cart"))


@customer_bp.route("/cart/clear", methods=["POST"])
@customer_required
def cart_clear():
    save_cart({})
    flash("Cart cleared.", "success")
    return redirect(url_for("customer.cart"))


@customer_bp.route("/cart")
@customer_required
def cart():
    items, total = cart_items_detailed()
    return render_template("customer/cart.html", items=items, total=total)


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

@customer_bp.route("/checkout", methods=["GET", "POST"])
@customer_required
def checkout():
    items, total = cart_items_detailed()
    if not items:
        flash("Your cart is empty.", "error")
        return redirect(url_for("customer.dashboard"))

    if request.method == "POST":
        payment_method = request.form.get("payment_method", PAYMENT_METHODS[0])
        if payment_method not in PAYMENT_METHODS:
            payment_method = PAYMENT_METHODS[0]

        # Re-check stock right before finalizing -- it may have changed
        # since the item was added to the cart.
        for entry in items:
            grocery = get_row_by_id(GROCERIES_FILE, "ItemID", entry["item_id"])
            if not grocery or int(grocery["QuantityInStock"]) < entry["quantity"]:
                flash(f'Not enough "{entry["name"]}" left in stock. Please update your cart.', "error")
                return redirect(url_for("customer.cart"))

        # Deduct stock for every line item.
        for entry in items:
            grocery = get_row_by_id(GROCERIES_FILE, "ItemID", entry["item_id"])
            new_qty = int(grocery["QuantityInStock"]) - entry["quantity"]
            update_row(GROCERIES_FILE, "ItemID", entry["item_id"], {"QuantityInStock": new_qty})

        # Log the order onto the customer's transaction history.
        customer_id = session["customer_id"]
        customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", customer_id)
        history = parse_transaction_history(customer.get("TransactionHistory"))
        order = {
            "order_id": len(history) + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # Named "line_items" rather than "items" so Jinja's dot syntax
            # (order.line_items) doesn't collide with dict.items(), the
            # built-in method every dict already has.
            "line_items": [
                {
                    "name": e["name"], "quantity": e["quantity"],
                    "unit": e["unit"], "unit_price": e["price"],
                    "subtotal": e["subtotal"],
                }
                for e in items
            ],
            "total": total,
            "payment_method": payment_method,
        }
        history.append(order)
        update_row(CUSTOMERS_FILE, "CustomerID", customer_id, {
            "TransactionHistory": serialize_transaction_history(history),
        })

        save_cart({})
        flash("Payment successful — your order has been placed.", "success")
        return redirect(url_for("customer.history"))

    return render_template("customer/checkout.html", items=items, total=total, payment_methods=PAYMENT_METHODS)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@customer_bp.route("/profile", methods=["GET", "POST"])
@customer_required
def profile():
    customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", session["customer_id"])

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()

        existing = get_row_by_email(CUSTOMERS_FILE, email)
        if not name or not email:
            flash("Name and email are required.", "error")
        elif existing and str(existing["CustomerID"]) != str(session["customer_id"]):
            flash("That email is already in use by another account.", "error")
        else:
            update_row(CUSTOMERS_FILE, "CustomerID", session["customer_id"], {
                "Name": name, "Email": email, "Phone": phone,
            })
            session["customer_name"] = name
            flash("Profile updated.", "success")
            customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", session["customer_id"])

    return render_template("customer/profile.html", customer=customer)


@customer_bp.route("/profile/password", methods=["POST"])
@customer_required
def change_password():
    customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", session["customer_id"])
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    if not check_password_hash(customer["PasswordHash"], current):
        flash("Current password is incorrect.", "error")
    elif new != confirm:
        flash("New passwords do not match.", "error")
    elif len(new) < 6:
        flash("New password must be at least 6 characters.", "error")
    else:
        update_row(CUSTOMERS_FILE, "CustomerID", session["customer_id"], {
            "PasswordHash": generate_password_hash(new),
        })
        flash("Password changed.", "success")

    return redirect(url_for("customer.profile"))


# ---------------------------------------------------------------------------
# Order history
# ---------------------------------------------------------------------------

@customer_bp.route("/history")
@customer_required
def history():
    customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", session["customer_id"])
    orders = list(reversed(parse_transaction_history(customer.get("TransactionHistory"))))
    return render_template("customer/history.html", orders=orders)
