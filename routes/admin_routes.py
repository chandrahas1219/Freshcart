from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from google_sheets_helpers import ADMINS_FILE, CUSTOMERS_FILE, GROCERIES_FILE, get_all_rows, get_row_by_id, get_row_by_email, create_record, update_row, parse_transaction_history
from decorators import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/verify-key", methods=["GET", "POST"])
def verify_key():
    if request.method == "POST":
        key = request.form.get("admin_key", "")
        if key == current_app.config["ADMIN_REGISTRATION_KEY"]:
            session["admin_key_verified"] = True
            return redirect(url_for("admin.register"))
        flash("That system key is not correct.", "error")
    return render_template("admin/verify_key.html")

@admin_bp.route("/register", methods=["GET", "POST"])
def register():
    if not session.get("admin_key_verified"):
        flash("Enter the admin system key first.", "error")
        return redirect(url_for("admin.verify_key"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not name or not email or not password:
            flash("Name, email, and password required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif get_row_by_email(ADMINS_FILE, email):
            flash("An admin account with that email already exists.", "error")
        else:
            create_record(ADMINS_FILE, "AdminID", {
                "Name": name, "Email": email, "Phone": phone,
                "PasswordHash": generate_password_hash(password),
                "CreatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            session.pop("admin_key_verified", None)
            flash("Admin account created. Please log in.", "success")
            return redirect(url_for("admin.login"))
    return render_template("admin/register.html")

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        admin = get_row_by_email(ADMINS_FILE, email)
        if admin and check_password_hash(admin["PasswordHash"], password):
            session["admin_id"] = str(admin["AdminID"])
            session["admin_name"] = admin["Name"]
            flash(f"Welcome back, {admin['Name']}.", "success")
            return redirect(url_for("admin.dashboard"))
        flash("Email and password do not match.", "error")
    return render_template("admin/login.html")

@admin_bp.route("/logout")
def logout():
    session.pop("admin_id", None)
    session.pop("admin_name", None)
    flash("Logged out.", "success")
    return redirect(url_for("index"))

@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    customers = get_all_rows(CUSTOMERS_FILE)
    groceries = get_all_rows(GROCERIES_FILE)
    low_stock = [g for g in groceries if int(g["QuantityInStock"]) <= 5]
    order_count = sum(len(parse_transaction_history(c.get("TransactionHistory"))) for c in customers)
    return render_template("admin/dashboard.html", customer_count=len(customers), item_count=len(groceries), order_count=order_count, low_stock=low_stock)

@admin_bp.route("/profile", methods=["GET", "POST"])
@admin_required
def profile():
    admin = get_row_by_id(ADMINS_FILE, "AdminID", session["admin_id"])
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        existing = get_row_by_email(ADMINS_FILE, email)
        if not name or not email:
            flash("Name and email required.", "error")
        elif existing and str(existing["AdminID"]) != str(session["admin_id"]):
            flash("Email already in use.", "error")
        else:
            update_row(ADMINS_FILE, "AdminID", session["admin_id"], {"Name": name, "Email": email, "Phone": phone})
            session["admin_name"] = name
            flash("Profile updated.", "success")
            admin = get_row_by_id(ADMINS_FILE, "AdminID", session["admin_id"])
    return render_template("admin/profile.html", admin=admin)

@admin_bp.route("/profile/password", methods=["POST"])
@admin_required
def change_password():
    admin = get_row_by_id(ADMINS_FILE, "AdminID", session["admin_id"])
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")
    if not check_password_hash(admin["PasswordHash"], current):
        flash("Current password incorrect.", "error")
    elif new != confirm:
        flash("New passwords do not match.", "error")
    elif len(new) < 6:
        flash("Password must be at least 6 characters.", "error")
    else:
        update_row(ADMINS_FILE, "AdminID", session["admin_id"], {"PasswordHash": generate_password_hash(new)})
        flash("Password changed.", "success")
    return redirect(url_for("admin.profile"))

@admin_bp.route("/customers")
@admin_required
def customers():
    all_customers = get_all_rows(CUSTOMERS_FILE)
    for c in all_customers:
        orders = parse_transaction_history(c.get("TransactionHistory"))
        c["orders"] = list(reversed(orders))
        c["order_count"] = len(orders)
        c["lifetime_spend"] = sum(o.get("total", 0) for o in orders)
    all_customers.sort(key=lambda c: c["Name"].lower())
    return render_template("admin/customers.html", customers=all_customers)

@admin_bp.route("/inventory")
@admin_required
def inventory():
    groceries = get_all_rows(GROCERIES_FILE)
    groceries.sort(key=lambda g: g["Name"].lower())
    return render_template("admin/inventory.html", groceries=groceries)

def _parse_price_and_quantity(form):
    try:
        price = float(form.get("price", "0"))
        quantity = int(float(form.get("quantity", "0")))
    except ValueError:
        return None, None, "Price and quantity must be valid numbers."
    if price <= 0:
        return None, None, "Price must be greater than 0."
    if quantity <= 0:
        return None, None, "Quantity must be greater than 0."
    return price, quantity, None

@admin_bp.route("/inventory/add", methods=["POST"])
@admin_required
def inventory_add():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    unit = request.form.get("unit", "").strip()
    image_url = request.form.get("image_url", "").strip()
    price, quantity, error = _parse_price_and_quantity(request.form)
    if not name or not unit:
        flash("Name and unit required.", "error")
    elif error:
        flash(error, "error")
    else:
        create_record(GROCERIES_FILE, "ItemID", {"Name": name, "Category": category, "Unit": unit, "PricePerUnit": price, "QuantityInStock": quantity, "ImageURL": image_url})
        flash(f'"{name}" added.', "success")
    return redirect(url_for("admin.inventory"))

@admin_bp.route("/inventory/edit/<item_id>", methods=["GET", "POST"])
@admin_required
def inventory_edit(item_id):
    item = get_row_by_id(GROCERIES_FILE, "ItemID", item_id)
    if not item:
        flash("Item no longer exists.", "error")
        return redirect(url_for("admin.inventory"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        unit = request.form.get("unit", "").strip()
        image_url = request.form.get("image_url", "").strip()
        price, quantity, error = _parse_price_and_quantity(request.form)
        if not name or not unit:
            flash("Name and unit required.", "error")
        elif error:
            flash(error, "error")
        else:
            update_row(GROCERIES_FILE, "ItemID", item_id, {"Name": name, "Category": category, "Unit": unit, "PricePerUnit": price, "QuantityInStock": quantity, "ImageURL": image_url})
            flash(f'"{name}" updated.', "success")
            return redirect(url_for("admin.inventory"))
        item = {**item, "Name": name, "Category": category, "Unit": unit, "ImageURL": image_url}
    return render_template("admin/inventory_edit.html", item=item)
