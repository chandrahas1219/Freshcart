from flask import Flask, render_template
from config import Config
from mongo_helpers import init_db
from routes.admin_routes import admin_bp
from routes.customer_routes import customer_bp
from routes.chat_routes import chat_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    init_db()
    app.register_blueprint(admin_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(chat_bp)
    @app.route("/")
    def index():
        return render_template("index.html")
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
