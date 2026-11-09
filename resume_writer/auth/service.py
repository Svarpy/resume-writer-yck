"""Local user authentication and profile/settings storage.

Login exists only to load user-specific data — there is no server session.
Passwords are hashed with bcrypt; plaintext is never stored.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Optional

import bcrypt

from resume_writer.paths import sanitize_username, user_profile_path, users_root

MIN_PASSWORD_LENGTH = 8
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")

# Process-local "current user" for UI convenience (logout clears this).
_current_username: Optional[str] = None


class AuthError(Exception):
    """Base class for authentication / profile errors."""


class UserExistsError(AuthError):
    pass


class UserNotFoundError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class PasswordValidationError(AuthError):
    pass


class NotSignedInError(AuthError):
    pass


@dataclass
class UserProfile:
    username: str
    password_hash: str
    display_name: str = ""
    email: str = ""
    dark_mode: bool = True
    primary_format_id: str = "default"
    created_at: str = ""
    updated_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        """Serializable profile without the password hash."""
        data = asdict(self)
        data.pop("password_hash", None)
        return data


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_username(username: str) -> str:
    raw = username.strip()
    if not USERNAME_RE.fullmatch(raw):
        raise PasswordValidationError(
            "Username must be 3–32 characters and use only letters, numbers, '.', '_' or '-'"
        )
    return sanitize_username(raw)


def validate_password(password: str, *, username: str = "") -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if password.strip() != password:
        raise PasswordValidationError("Password must not start or end with whitespace")
    if password.isspace():
        raise PasswordValidationError("Password cannot be blank")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise PasswordValidationError("Password must include at least one letter and one number")
    if username and password.casefold() == username.casefold():
        raise PasswordValidationError("Password must not match the username")


def _load_profile(username: str) -> UserProfile:
    path = user_profile_path(username)
    if not path.is_file():
        raise UserNotFoundError(f"User '{username}' not found")
    raw = json.loads(path.read_text(encoding="utf-8"))
    extra = raw.pop("extra", {}) or {}
    # Absorb unknown top-level keys into extra for forward compatibility.
    known = {f.name for f in fields(UserProfile)}
    for key in list(raw.keys()):
        if key not in known:
            extra[key] = raw.pop(key)
    return UserProfile(extra=extra, **raw)


def _save_profile(profile: UserProfile) -> None:
    profile.updated_at = _utc_now()
    path = user_profile_path(profile.username)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(profile)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def user_exists(username: str) -> bool:
    try:
        key = sanitize_username(username)
    except ValueError:
        return False
    return user_profile_path(key).is_file()


def list_usernames() -> list[str]:
    root = users_root()
    names: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "profile.json").is_file():
            names.append(child.name)
    return names


def signup(
    username: str,
    password: str,
    *,
    display_name: str = "",
    email: str = "",
    dark_mode: bool = True,
    primary_format_id: str = "default",
) -> UserProfile:
    """Create a new local user. Returns the public profile and signs them in."""
    key = validate_username(username)
    validate_password(password, username=key)
    if user_exists(key):
        raise UserExistsError(f"Username '{key}' is already taken")

    now = _utc_now()
    profile = UserProfile(
        username=key,
        password_hash=_hash_password(password),
        display_name=(display_name or key).strip(),
        email=email.strip(),
        dark_mode=bool(dark_mode),
        primary_format_id=primary_format_id or "default",
        created_at=now,
        updated_at=now,
    )
    _save_profile(profile)
    set_current_user(key)
    return profile


def signin(username: str, password: str) -> UserProfile:
    """Verify credentials and set the process-local current user."""
    try:
        key = sanitize_username(username)
    except ValueError as exc:
        raise InvalidCredentialsError("Invalid username or password") from exc
    try:
        profile = _load_profile(key)
    except UserNotFoundError as exc:
        raise InvalidCredentialsError("Invalid username or password") from exc
    if not _verify_password(password, profile.password_hash):
        raise InvalidCredentialsError("Invalid username or password")
    set_current_user(key)
    return profile


def change_password(username: str, old_password: str, new_password: str) -> UserProfile:
    """Change password using old + new only (no OTP)."""
    key = sanitize_username(username)
    profile = _load_profile(key)
    if not _verify_password(old_password, profile.password_hash):
        raise InvalidCredentialsError("Current password is incorrect")
    validate_password(new_password, username=key)
    if old_password == new_password:
        raise PasswordValidationError("New password must be different from the current password")
    profile.password_hash = _hash_password(new_password)
    _save_profile(profile)
    return profile


def get_profile(username: str) -> UserProfile:
    return _load_profile(sanitize_username(username))


def update_profile(
    username: str,
    *,
    display_name: Optional[str] = None,
    email: Optional[str] = None,
    dark_mode: Optional[bool] = None,
    primary_format_id: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> UserProfile:
    """Update mutable profile/settings fields (not password)."""
    profile = _load_profile(sanitize_username(username))
    if display_name is not None:
        profile.display_name = display_name.strip()
    if email is not None:
        profile.email = email.strip()
    if dark_mode is not None:
        profile.dark_mode = bool(dark_mode)
    if primary_format_id is not None:
        profile.primary_format_id = primary_format_id.strip() or "default"
    if extra is not None:
        profile.extra = {**profile.extra, **extra}
    _save_profile(profile)
    return profile


def get_settings(username: str) -> dict[str, Any]:
    """Convenience: public profile + settings dict for the UI."""
    profile = get_profile(username)
    return profile.public_dict()


def set_current_user(username: Optional[str]) -> None:
    global _current_username
    if username is None:
        _current_username = None
        return
    _current_username = sanitize_username(username)


def get_current_user() -> Optional[str]:
    return _current_username


def clear_session() -> None:
    """UI logout helper — clears the process-local current user."""
    set_current_user(None)


def require_current_user() -> str:
    if not _current_username:
        raise NotSignedInError("No user is signed in")
    return _current_username


def get_current_profile() -> UserProfile:
    return get_profile(require_current_user())
