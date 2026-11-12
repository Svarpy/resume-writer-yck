"""MongoDB access: connection and the small repository classes the services use."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from resume_server.config import ServerConfig


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(config: ServerConfig) -> Database:
    client = MongoClient(config.mongodb_uri, serverSelectionTimeoutMS=8000, tz_aware=True)
    return client[config.mongodb_db]


DEFAULT_ROLE = "user"
ADMIN_ROLE = "admin"  # set by hand in the users collection
COLLECTIONS = ("users", "api_tokens", "formats", "format_files", "settings", "system")


def ensure_indexes(db: Database) -> None:
    """Create every collection (MongoDB otherwise creates them lazily on first write) and the indexes."""
    existing = set(db.list_collection_names())
    for name in COLLECTIONS:
        if name not in existing:
            db.create_collection(name)
    db.api_tokens.create_index([("hash", ASCENDING)], unique=True)
    db.api_tokens.create_index([("user", ASCENDING)])
    db.formats.create_index([("user", ASCENDING), ("created_ns", ASCENDING)])
    db.settings.create_index([("user", ASCENDING)])


class UserRepo:
    def __init__(self, db: Database) -> None:
        self.users = db.users

    def get(self, username: str) -> Optional[dict[str, Any]]:
        return self.users.find_one({"_id": username})

    def insert(self, doc: dict[str, Any]) -> None:
        self.users.insert_one(doc)

    def backfill_roles(self) -> None:
        """Accounts created before roles existed get the default role."""
        self.users.update_many({"role": {"$exists": False}}, {"$set": {"role": DEFAULT_ROLE}})

    def role(self, username: str) -> str:
        return str((self.get(username) or {}).get("role") or DEFAULT_ROLE)

    def update(self, username: str, fields: dict[str, Any], inc: Optional[dict[str, int]] = None) -> None:
        operation: dict[str, Any] = {"$set": {**fields, "updated_at": now_iso()}}
        if inc:
            operation["$inc"] = inc
        self.users.update_one({"_id": username}, operation)


class TokenRepo:
    def __init__(self, db: Database) -> None:
        self.tokens = db.api_tokens

    def insert(self, doc: dict[str, Any]) -> None:
        self.tokens.insert_one(doc)

    def by_hash(self, token_hash: str) -> Optional[dict[str, Any]]:
        return self.tokens.find_one({"hash": token_hash})

    def touch(self, token_id: str) -> None:
        self.tokens.update_one({"_id": token_id}, {"$set": {"last_used_at": now_iso()}})

    def for_user(self, username: str) -> list[dict[str, Any]]:
        return list(self.tokens.find({"user": username}).sort("created_at", ASCENDING))

    def delete(self, username: str, token_id: str) -> bool:
        return self.tokens.delete_one({"_id": token_id, "user": username}).deleted_count == 1


class FormatRepo:
    """Format metadata (``formats``) and the sample documents (``format_files``)."""

    def __init__(self, db: Database) -> None:
        self.formats = db.formats
        self.files = db.format_files

    def insert(self, doc: dict[str, Any], data: bytes) -> None:
        self.formats.insert_one(doc)
        self.files.insert_one({"_id": doc["_id"], "user": doc["user"], "data": data})

    def get(self, username: str, format_id: str) -> Optional[dict[str, Any]]:
        return self.formats.find_one({"_id": format_id, "user": username})

    def list(self, username: str) -> list[dict[str, Any]]:
        return list(self.formats.find({"user": username}).sort([("created_ns", ASCENDING), ("_id", ASCENDING)]))

    def file(self, username: str, format_id: str) -> Optional[bytes]:
        doc = self.files.find_one({"_id": format_id, "user": username})
        return bytes(doc["data"]) if doc else None

    def replace(self, username: str, format_id: str, fields: dict[str, Any], data: bytes) -> Optional[dict[str, Any]]:
        """Swap the template document and metadata of a format in place (same id, same owner)."""
        doc = self.formats.find_one_and_update(
            {"_id": format_id, "user": username}, {"$set": fields, "$inc": {"rev": 1, "settings_rev": 1}},
            return_document=True)
        if doc is not None:
            self.files.update_one({"_id": format_id, "user": username}, {"$set": {"data": data}})
        return doc

    def delete(self, username: str, format_id: str) -> bool:
        self.files.delete_one({"_id": format_id, "user": username})
        return self.formats.delete_one({"_id": format_id, "user": username}).deleted_count == 1

    def bump_settings_rev(self, format_id: str) -> int:
        doc = self.formats.find_one_and_update({"_id": format_id}, {"$inc": {"settings_rev": 1}}, return_document=True)
        return int(doc["settings_rev"]) if doc else 0

    def set_format_overrides(self, format_id: str, overrides: dict[str, Any]) -> int:
        self.formats.update_one({"_id": format_id}, {"$set": {"overrides": overrides}})
        return self.bump_settings_rev(format_id)


class SettingsRepo:
    """User-wide setting overrides (one document per user)."""

    def __init__(self, db: Database) -> None:
        self.settings = db.settings

    def get(self, username: str) -> dict[str, Any]:
        doc = self.settings.find_one({"_id": username})
        return doc or {"_id": username, "overrides": {}, "rev": 0}

    def set_overrides(self, username: str, overrides: dict[str, Any]) -> int:
        doc = self.settings.find_one_and_update(
            {"_id": username},
            {"$set": {"user": username, "overrides": overrides}, "$inc": {"rev": 1}},
            upsert=True, return_document=True,
        )
        return int(doc["rev"])
