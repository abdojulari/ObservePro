from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.scrypt(
        password.encode(),
        salt=salt.encode(),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, digest = encoded.split("$")
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode(),
            salt=salt.encode(),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(derived.hex(), digest)
    except (ValueError, TypeError):
        return False


def generate_api_key() -> tuple[str, str, str]:
    secret = "op_" + secrets.token_urlsafe(32)
    prefix = secret[:12]
    digest = hashlib.sha256(secret.encode()).hexdigest()
    return secret, prefix, digest


def hash_api_key(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def create_access_token(*, user_id: str, email: str, role: str) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
