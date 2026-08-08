"""Security helpers: PBKDF2 password hashing + JWT tokens.

- Password hashing uses stdlib ``hashlib.pbkdf2_hmac`` (SHA-256,
  600 000 iterations, per-user random salt) — no exotic C extensions,
  FIPS-friendly, secure for this threat model.
- Tokens use PyJWT HS256 signed with the app SECRET_KEY.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import get_settings

_ALGO = "sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != f"pbkdf2_{_ALGO}":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac(
            _ALGO, password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(candidate, expected)
    except (ValueError, AttributeError):
        return False


# --------------------------------------------------------------------------
# JWTs
# --------------------------------------------------------------------------

def create_access_token(user_id: int, email: str) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token, expires_in


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise PermissionError("Token has expired") from None
    except jwt.InvalidTokenError as exc:
        raise PermissionError(f"Invalid token: {exc}") from None


def encrypt_token(secret: str) -> str:
    """At-rest obfuscation for OAuth tokens (FERNET-style XOR with keyed HMAC).

    Not encryption-grade by itself — pairs with keeping SECRET_KEY out of
    source control.  Use KMS/HSM for production at scale.
    """
    key = hashlib.sha256(get_settings().SECRET_KEY.encode()).digest()
    nonce = os.urandom(12)
    stream = _keystream(key, nonce, len(secret.encode()))
    cipher = bytes(c ^ k for c, k in zip(secret.encode(), stream))
    return f"v1.{nonce.hex()}.{cipher.hex()}"


def decrypt_token(payload: str) -> str:
    version, nonce_hex, cipher_hex = payload.split(".")
    key = hashlib.sha256(get_settings().SECRET_KEY.encode()).digest()
    nonce = bytes.fromhex(nonce_hex)
    cipher = bytes.fromhex(cipher_hex)
    stream = _keystream(key, nonce, len(cipher))
    return bytes(c ^ k for c, k in zip(cipher, stream)).decode()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(out[:length])