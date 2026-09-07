import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# Default local Postgres connection — override with DATABASE_URL in
# production (e.g. your managed Postgres instance's connection string).


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret")
    # Used to derive the Fernet key that encrypts sensitive SystemSetup
    # fields (default_code_type / default_generation_level) at rest.
    # Set a real 32+ byte secret in production via the environment.
    FIELD_ENCRYPTION_KEY = "dev-field-encryption-key-change-me"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    
    
    # ── Database configuration ─────────────────────────────────────────────
    DB_USER = "postgres"
    DB_PASSWORD = "root"
    DB_HOST = "localhost"
    DB_PORT = "5432"
    DB_NAME = "bottle_mgmt"
    SCAN_BASE_URL = "http://localhost:5000"

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 20,
        "max_overflow": 40,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }
    SQLALCHEMY_ECHO = False
    CORS_ORIGIN = "http://localhost:5173"
