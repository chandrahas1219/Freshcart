"""Route guards for the two portals. Each checks the session for the
matching login marker and bounces anonymous visitors to that portal's
login page with a flash message explaining why."""

from functools import wraps
from flask import session, redirect, url_for, flash


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in as an admin to continue.", "error")
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


def customer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "customer_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("customer.login"))
        return view(*args, **kwargs)
    return wrapped
