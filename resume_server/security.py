"""Password hashing, login tokens (JWT) and personal access tokens."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from resume_server.errors import UnauthorizedError, ValidationFailed

MIN_PASSWORD_LENGTH = 8
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
TOKEN_PREFIX = "rwt_"


def normalize_username(username: str) -> str:
    raw = (username or "").strip()
    if not USERNAME_RE.fullmatch(raw):
        raise ValidationFailed("Username must be 3-32 characters and use only letters, numbers, '.', '_' or '-'")
    return raw.lower()


def validate_password(password: str, username: str = "") -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationFailed(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if password.strip() != password:
        raise ValidationFailed("Password must not start or end with whitespace")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationFailed("Password must include at least one letter and one number")
    if username and password.casefold() == username.casefold():
        raise ValidationFailed("Password must not match the username")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_login_token(username: str, secret: str, expire_hours: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "iat": now, "exp": now + timedelta(hours=expire_hours), "typ": "login"}
    return jwt.encode(payload, secret, algorithm="HS256")


def read_login_token(token: str, secret: str) -> str:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired login token") from exc
    if payload.get("typ") != "login" or not payload.get("sub"):
        raise UnauthorizedError("Invalid login token")
    return str(payload["sub"])


def new_access_token() -> tuple[str, str]:
    """``(plain token shown once, sha256 hash stored)``."""
    plain = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return plain, hash_token(plain)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
