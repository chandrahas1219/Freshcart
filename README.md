# FreshCart Market

A grocery ordering web app with separate **customer** and **admin**
portals, built on Flask — using three Excel files as the database instead
of a real DBMS.

## Quick start

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**. That's it — `admins.xlsx`, `customers.xlsx`,
and `groceries.xlsx` are created automatically inside `data/` the first
time the app runs, with the correct headers already in place.

### Creating your first admin account

Admin registration is gated by a system key so random visitors can't make
themselves an admin. The default key is:

```
SECRET123
```

Change it before you rely on this anywhere but your own machine:

```bash
export ADMIN_KEY="something-only-your-staff-know"
export FLASK_SECRET_KEY="a-long-random-string"   # signs session cookies
python app.py
```

## Project layout

```
app.py                  entry point — creates the app, registers routes
config.py                SECRET_KEY / ADMIN_KEY, overridable via env vars
excel_helpers.py         all reads/writes to the .xlsx files live here
decorators.py            @admin_required / @customer_required route guards
cart_utils.py            session-based cart (see "Design notes" below)
routes/
  admin_routes.py         registration gate, login, dashboard, inventory,
                           customer/order visibility, profile
  customer_routes.py       registration, login, browsing, cart, checkout,
                            profile, order history
templates/                Jinja2 templates (base.html + admin/ + customer/)
static/                   Tailwind config lives in base.html; style.css
                          holds the rest, main.js is a small progressive
                          enhancement layer
data/                     the three .xlsx files (created on first run)
tests/smoke_test.py       an end-to-end sanity check, safe to run any time
```

## Running the tests

`tests/smoke_test.py` drives the app through Flask's test client — admin
registration, inventory, customer registration, cart, checkout, stock
deduction, password changes, and access control — using a throwaway temp
directory, so it never touches your real `data/` files:

```bash
python tests/smoke_test.py
```

## Design notes & trade-offs

- **The cart lives in the session, not a 4th spreadsheet.** It's
  short-lived, per-visitor state, so a signed cookie is a better fit than
  another Excel file. It only becomes durable once an order is placed —
  at that point it's written into the customer's `TransactionHistory` and
  the session cart is cleared.
- **Quantities are whole numbers.** "50 kg in stock" means 50 one-kg units;
  the cart's +/- controls move one unit at a time. This keeps the UI and
  the stock math simple and avoids floating-point edge cases. Prices can
  still have paise (₹45.50), quantities can't.
- **Stock is re-checked at checkout**, not just when adding to cart, in
  case someone else bought the last of an item in between.
- **No CSRF protection or rate limiting.** Flask-WTF (or similar) would be
  the natural next addition if this ever needs to handle untrusted traffic.
- **Concurrency is intentionally simple.** Every read/write opens the
  workbook, does its work, and saves/closes immediately, guarded by an
  in-process lock — fine for the Flask dev server's default single worker,
  not a substitute for a real database under real concurrent load. If you
  outgrow this, the natural next step is swapping `excel_helpers.py` for a
  SQLite-backed version with the same function signatures — nothing in
  `routes/` would need to change.
- **`debug=True` and `host="127.0.0.1"`** in `app.py` are both meant for
  local development only. Turn debug off and put a real WSGI server (e.g.
  gunicorn) in front before exposing this beyond your own machine.

## Possible enhancements

- AJAX cart updates (currently a full page reload per +/- click, by design
  — see the trade-off note above)
- Product search/filtering and category pages
- Order status beyond "placed" (packed, delivered, etc.)
- CSV export of inventory or customer data from the admin dashboard
