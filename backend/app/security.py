from datetime import datetime, timedelta, timezone

import secrets

import jwt
from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()
# Verify unknown accounts too, so they follow the same password-hash work path.
dummy_hash = password_hasher.hash("not-a-user-password")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return password_hasher.verify(password, stored_hash)
    except Exception:
        return False


def issue_token(user_id: int, settings, token_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now,
                       "exp": now + timedelta(minutes=settings.access_token_minutes),
                       "iss": "ntou-events", "aud": "ntou-events-api",
                       "jti": secrets.token_urlsafe(24), "ver": token_version},
                      settings.jwt_secret, algorithm="HS256")


def decode_token(token: str, settings) -> dict:
    """Return the verified claims; callers read sub, jti and exp."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"],
                      issuer="ntou-events", audience="ntou-events-api",
                      options={"require": ["sub", "exp", "iat", "iss", "aud", "jti"]})
