import os

class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-please-change-in-production")
    ADMIN_REGISTRATION_KEY = os.environ.get("ADMIN_KEY", "SECRET123")
