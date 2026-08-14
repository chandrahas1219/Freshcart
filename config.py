import os

class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-please-change-in-production")
    ADMIN_REGISTRATION_KEY = os.environ.get("ADMIN_KEY", "SECRET123")

    # SMTP settings for order receipt emails. Leave SMTP_HOST unset to
    # disable emails entirely (checkout will keep working either way).
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "")  # defaults to SMTP_USER if blank
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() != "false"
