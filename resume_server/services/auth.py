"""Authentication service: accounts, login tokens and personal access tokens."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from pymongo.errors import DuplicateKeyError

from resume_server import security
from resume_server.config import ServerConfig
from resume_server.db import DEFAULT_ROLE, TokenRepo, UserRepo, now_iso
from resume_server.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationFailed
from resume_server.services.settings import SettingsService


def public_profile(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": doc["_id"],
        "display_name": doc.get("display_name", ""),
        "email": doc.get("email", ""),
        "default_format_id": doc.get("default_format_id", ""),
        "role": doc.get("role") or DEFAULT_ROLE,
        "created_at": doc.get("created_at", ""),
    }


class AuthService:
    def __init__(self, users: UserRepo, tokens: TokenRepo, settings: SettingsService, config: ServerConfig) -> None:
        self.users, self.tokens, self.settings, self.config = users, tokens, settings, config

    # -- accounts -------------------------------------------------------------------
    def signup(self, username: str, password: str, display_name: str = "", email: str = "") -> dict[str, Any]:
        key = security.normalize_username(username)
        security.validate_password(password, key)
        doc = {
            "_id": key, "password_hash": security.hash_password(password),
            "display_name": (display_name or key).strip(), "email": (email or "").strip(),
            "role": DEFAULT_ROLE, "default_format_id": "", "revs": {"formats": 0}, "created_at": now_iso(), "updated_at": now_iso(),
        }
        try:
            self.users.insert(doc)
        except DuplicateKeyError as exc:
            raise ConflictError(f"Username '{key}' is already taken") from exc
        seed = {"personal.name": doc["display_name"]}
        if doc["email"]:
            seed["personal.email"] = doc["email"]
        self.settings.seed_user(key, seed)
        return public_profile(doc)

    def login(self, username: str, password: str) -> tuple[str, dict[str, Any]]:
        try:
            key = security.normalize_username(username)
        except ValidationFailed:
            raise UnauthorizedError("Invalid username or password") from None
        doc = self.users.get(key)
        if doc is None or not security.verify_password(password, doc["password_hash"]):
            raise UnauthorizedError("Invalid username or password")
        token = security.create_login_token(key, self.config.jwt_secret, self.config.jwt_expire_hours)
        return token, public_profile(doc)

    def profile(self, username: str) -> dict[str, Any]:
        doc = self.users.get(username)
        if doc is None:
            raise NotFoundError("User not found")
        return public_profile(doc)

    def update_profile(self, username: str, display_name: Optional[str], email: Optional[str]) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if display_name is not None:
            changes["display_name"] = display_name.strip()
        if email is not None:
            changes["email"] = email.strip()
        if changes:
            self.users.update(username, changes)
        return self.profile(username)

    def change_password(self, username: str, old: str, new: str) -> None:
        doc = self.users.get(username)
        if doc is None or not security.verify_password(old, doc["password_hash"]):
            raise UnauthorizedError("Current password is incorrect")
        security.validate_password(new, username)
        if old == new:
            raise ValidationFailed("New password must be different from the current password")
        self.users.update(username, {"password_hash": security.hash_password(new)})

    # -- tokens ---------------------------------------------------------------------
    def authenticate(self, bearer: str) -> str:
        """Username for a login token (JWT) or a personal access token."""
        token = (bearer or "").strip()
        if token.startswith(security.TOKEN_PREFIX):
            doc = self.tokens.by_hash(security.hash_token(token))
            if doc is None:
                raise UnauthorizedError("Invalid access token")
            self.tokens.touch(doc["_id"])
            return doc["user"]
        username = security.read_login_token(token, self.config.jwt_secret)
        if self.users.get(username) is None:
            raise UnauthorizedError("Account no longer exists")
        return username

    def create_access_token(self, username: str, name: str) -> dict[str, Any]:
        name = (name or "").strip() or "token"
        plain, token_hash = security.new_access_token()
        doc = {"_id": uuid.uuid4().hex[:12], "user": username, "name": name, "hash": token_hash,
               "prefix": plain[:10], "created_at": now_iso(), "last_used_at": ""}
        self.tokens.insert(doc)
        return {"id": doc["_id"], "name": name, "token": plain, "prefix": doc["prefix"], "created_at": doc["created_at"]}

    def list_access_tokens(self, username: str) -> list[dict[str, Any]]:
        return [{"id": d["_id"], "name": d["name"], "prefix": d["prefix"], "created_at": d["created_at"],
                 "last_used_at": d.get("last_used_at", "")} for d in self.tokens.for_user(username)]

    def revoke_access_token(self, username: str, token_id: str) -> None:
        if not self.tokens.delete(username, token_id):
            raise NotFoundError("Token not found")
