"""
FreshCart Market -- a lightweight grocery ordering app backed by three
Excel files instead of a database.

Run it with:
    python app.py

Then open http://127.0.0.1:5000 in a browser.
"""

from flask import Flask, render_template

from config import Config
from excel_helpers import init_excel_files
from routes.admin_routes import admin_bp
from routes.customer_routes import customer_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Make sure admins.xlsx, customers.xlsx, and groceries.xlsx exist
    # (with correct headers) before any request is handled.
    init_excel_files()

    app.register_blueprint(admin_bp)
    app.register_blueprint(customer_bp)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app


app = create_app()

if __name__ == "__main__":
    # host is explicitly local-only; debug=True is meant for development,
    # not for exposing this app on a network. See README.md before
    # deploying this anywhere beyond your own machine.
    app.run(debug=True, host="127.0.0.1", port=5000)
