"""
A self-contained sanity check for the main flows in the app: admin
registration/login, inventory, customer registration/login, cart,
checkout, stock deduction, and transaction history.

It points the app at a throwaway temp directory (via the
GROCERY_APP_DATA_DIR environment variable) BEFORE importing the app, so
running this will never touch your real data/*.xlsx files.

Run it from the project root:
    python tests/smoke_test.py
"""

import os
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.environ["GROCERY_APP_DATA_DIR"] = tempfile.mkdtemp(prefix="freshcart_smoke_test_")

from app import app  # noqa: E402
from excel_helpers import get_all_rows, GROCERIES_FILE  # noqa: E402

client = app.test_client()
failures = []


def check(resp, expected, label):
    expected_list = expected if isinstance(expected, (list, tuple)) else [expected]
    ok = resp.status_code in expected_list
    print(f"[{'ok' if ok else 'FAIL'}] {label} (status {resp.status_code})")
    if not ok:
        failures.append(label)
        print(resp.data[:400])
    return ok


def expect(condition, label):
    print(f"[{'ok' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)


print("== Admin flow ==")
check(client.get("/admin/verify-key"), 200, "GET verify-key")
check(client.post("/admin/verify-key", data={"admin_key": "SECRET123"}, follow_redirects=True), 200, "verify correct key")
check(client.post("/admin/register", data={
    "name": "Test Admin", "email": "admin@test.com", "phone": "1234567890",
    "password": "adminpass123", "confirm_password": "adminpass123",
}, follow_redirects=True), 200, "register admin")
r = check(client.post("/admin/login", data={"email": "admin@test.com", "password": "adminpass123"}, follow_redirects=True), 200, "admin login")
check(client.get("/admin/dashboard"), 200, "admin dashboard")

r = client.post("/admin/inventory/add", data={
    "name": "Tomato", "category": "Vegetables", "unit": "kg",
    "price": "40", "quantity": "50", "image_url": "",
}, follow_redirects=True)
check(r, 200, "add grocery item")

r = client.post("/admin/inventory/add", data={
    "name": "Bad Item", "category": "Test", "unit": "kg",
    "price": "0", "quantity": "10", "image_url": "",
}, follow_redirects=True)
expect(b"greater than 0" in r.data, "rejects zero price")

r = client.get("/admin/inventory")
check(r, 200, "inventory page")
expect(b"Tomato" in r.data, "inventory lists Tomato")
expect(b"Bad Item" not in r.data, "invalid item was not created")

client.get("/admin/logout")

print("\n== Customer flow ==")
check(client.post("/customer/register", data={
    "name": "Test Customer", "email": "cust@test.com", "phone": "9876543210",
    "password": "custpass123", "confirm_password": "custpass123",
}, follow_redirects=True), 200, "register customer")
check(client.post("/customer/login", data={"email": "cust@test.com", "password": "custpass123"}, follow_redirects=True), 200, "customer login")

r = client.get("/customer/dashboard")
check(r, 200, "customer dashboard")
expect(b"Tomato" in r.data, "customer sees Tomato")

groceries = get_all_rows(GROCERIES_FILE)
item_id = str(groceries[0]["ItemID"])

for _ in range(3):
    check(client.post(f"/customer/cart/add/{item_id}", follow_redirects=True), 200, "add to cart")
check(client.post(f"/customer/cart/decrement/{item_id}", follow_redirects=True), 200, "decrement cart")

r = client.get("/customer/cart")
check(r, 200, "view cart")
expect(b"Tomato" in r.data, "cart shows Tomato")

check(client.get("/customer/checkout"), 200, "checkout page")
r = client.post("/customer/checkout", data={"payment_method": "UPI"}, follow_redirects=True)
check(r, 200, "submit checkout")
expect(b"UPI" in r.data, "history shows UPI payment")

groceries_after = get_all_rows(GROCERIES_FILE)
new_qty = int(groceries_after[0]["QuantityInStock"])
expect(new_qty == 48, f"stock deducted correctly (50 - 2 = 48, got {new_qty})")

r = client.get("/customer/history")
check(r, 200, "order history page")

client.get("/customer/logout")

print("\n== Admin sees the order ==")
client.post("/admin/login", data={"email": "admin@test.com", "password": "adminpass123"}, follow_redirects=True)
r = client.get("/admin/customers")
check(r, 200, "admin customers page")
expect(b"Test Customer" in r.data, "admin sees Test Customer")
expect(b"UPI" in r.data, "admin sees the UPI order")

print("\n== Edge cases ==")

# Duplicate email registrations should be rejected
r = client.post("/customer/register", data={
    "name": "Dupe", "email": "cust@test.com", "phone": "111",
    "password": "somepass1", "confirm_password": "somepass1",
}, follow_redirects=True)
expect(b"already exists" in r.data, "duplicate customer email rejected")

client.post("/admin/verify-key", data={"admin_key": "SECRET123"}, follow_redirects=True)
r = client.post("/admin/register", data={
    "name": "Dupe Admin", "email": "admin@test.com", "phone": "111",
    "password": "somepass1", "confirm_password": "somepass1",
}, follow_redirects=True)
expect(b"already exists" in r.data, "duplicate admin email rejected")

# Wrong admin key should not grant access to the registration form
client2 = app.test_client()
r = client2.post("/admin/verify-key", data={"admin_key": "WRONG"}, follow_redirects=True)
expect(b"not correct" in r.data, "wrong admin key rejected")
r = client2.get("/admin/register", follow_redirects=True)
expect(b"Enter the admin system key" in r.data or b"system key" in r.data, "register blocked without verified key")

# Wrong login credentials
client3 = app.test_client()
r = client3.post("/customer/login", data={"email": "cust@test.com", "password": "wrongpass"}, follow_redirects=True)
expect(b"do not match" in r.data, "wrong customer password rejected")

# Protected routes redirect anonymous visitors to login
client4 = app.test_client()
r = client4.get("/customer/dashboard", follow_redirects=True)
expect(b"Log in" in r.data or b"log in" in r.data.lower(), "anonymous visitor redirected to login")
r = client4.get("/admin/dashboard", follow_redirects=True)
expect(b"log in" in r.data.lower(), "anonymous admin visitor redirected to login")

# Password change requires the correct current password
client.post("/customer/login", data={"email": "cust@test.com", "password": "custpass123"}, follow_redirects=True)
r = client.post("/customer/profile/password", data={
    "current_password": "wrongcurrent", "new_password": "newpass123", "confirm_password": "newpass123",
}, follow_redirects=True)
expect(b"incorrect" in r.data, "password change rejects wrong current password")

r = client.post("/customer/profile/password", data={
    "current_password": "custpass123", "new_password": "newpass123", "confirm_password": "newpass123",
}, follow_redirects=True)
expect(b"changed" in r.data, "password change accepts correct current password")
client.get("/customer/logout")
check(client.post("/customer/login", data={"email": "cust@test.com", "password": "newpass123"}, follow_redirects=True), 200, "login works with new password")

# Cart can't exceed available stock, and decrementing to 0 removes the line
client.post("/customer/login", data={"email": "cust@test.com", "password": "newpass123"}, follow_redirects=True)
groceries = get_all_rows(GROCERIES_FILE)
item_id = str(groceries[0]["ItemID"])
current_stock = int(groceries[0]["QuantityInStock"])
for _ in range(current_stock + 5):
    client.post(f"/customer/cart/add/{item_id}", follow_redirects=True)
with client.session_transaction() as sess:
    cart_qty = sess.get("cart", {}).get(item_id, 0)
expect(cart_qty == current_stock, f"cart add is capped at available stock ({current_stock}, got {cart_qty})")

for _ in range(cart_qty):
    client.post(f"/customer/cart/decrement/{item_id}", follow_redirects=True)
with client.session_transaction() as sess:
    expect(item_id not in sess.get("cart", {}), "decrementing to 0 removes the cart line")

# Admin can edit an existing inventory item
client.get("/customer/logout")
client.post("/admin/login", data={"email": "admin@test.com", "password": "adminpass123"}, follow_redirects=True)
r = client.post(f"/admin/inventory/edit/{item_id}", data={
    "name": "Tomato (Hybrid)", "category": "Vegetables", "unit": "kg",
    "price": "45", "quantity": "30", "image_url": "",
}, follow_redirects=True)
check(r, 200, "edit inventory item")
expect(b"Tomato (Hybrid)" in r.data, "inventory shows edited name")

print("\n" + "=" * 40)
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
