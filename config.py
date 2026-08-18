import os

class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-please-change-in-production")
    ADMIN_REGISTRATION_KEY = os.environ.get("ADMIN_KEY", "SECRET123")

    # Order receipt emails go through Brevo's HTTP API (not raw SMTP).
    # Render's free tier blocks outbound SMTP ports (25/465/587) entirely,
    # so smtplib will always hang/fail there regardless of credentials.
    # Brevo's API runs over plain HTTPS (443), which isn't blocked, and
    # the free plan (300 emails/day) needs no credit card.
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
    SENDER_NAME = os.environ.get("SENDER_NAME", "FreshCart")
