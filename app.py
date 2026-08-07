from flask import Flask, render_template
from config import Config
from google_sheets_helpers import init_excel_files
from routes.admin_routes import admin_bp
from routes.customer_routes import customer_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    init_excel_files()
    app.register_blueprint(admin_bp)
    app.register_blueprint(customer_bp)
    @app.route("/")
    def index():
        return render_template("index.html")
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
