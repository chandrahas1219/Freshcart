"""
Application configuration.

Values can be overridden with environment variables so you never have to
hard-code secrets in source control:

    export FLASK_SECRET_KEY="something-long-and-random"
    export ADMIN_KEY="a-key-you-share-only-with-store-staff"
"""

import os


class Config:
    # Signs session cookies. Change this to a long random string in production.
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-please-change-in-production")

    # An admin must type this key correctly before the registration form appears.
    # Share it only with people you want to be able to create admin accounts.
    ADMIN_REGISTRATION_KEY = os.environ.get("ADMIN_KEY", "SECRET123")
