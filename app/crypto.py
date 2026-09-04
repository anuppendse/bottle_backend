import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from sqlalchemy.types import TypeDecorator, String


def _fernet():
    """Derives a stable 32-byte Fernet key from FIELD_ENCRYPTION_KEY so
    the config can hold a plain human-chosen secret rather than a
    pre-formatted Fernet key."""
    key_material = current_app.config.get("FIELD_ENCRYPTION_KEY") or current_app.config["SECRET_KEY"]
    digest = hashlib.sha256(key_material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedString(TypeDecorator):
    """A string column that is encrypted at rest with Fernet
    (AES-128-CBC + HMAC) and transparently decrypted on read. Use for
    sensitive config values that must not be stored as plaintext in
    the database."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Defensive fallback for rows written before encryption was
            # enabled — avoids hard-crashing reads on legacy plaintext.
            return value
