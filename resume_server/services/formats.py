"""Format service: upload a sample document, list/delete formats, choose the default."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Optional

from resume_core.formats import FormatError, analyze_sample
from resume_core.sanitize import sanitize_sample
from resume_server.config import ServerConfig
from resume_server.db import FormatRepo, UserRepo, now_iso
from resume_server.errors import NotFoundError, ValidationFailed


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "format"


def public_format(doc: dict[str, Any], default_id: str) -> dict[str, Any]:
    keys = ("font_name", "name_size", "heading_size", "body_size", "sections", "warnings", "created_at", "sanitized")
    return {"id": doc["_id"], "name": doc["name"], "is_default": doc["_id"] == default_id,
            "rev": int(doc.get("rev", 0)), **{k: doc.get(k) for k in keys}}


class FormatService:
    def __init__(self, formats: FormatRepo, users: UserRepo, config: ServerConfig) -> None:
        self.formats, self.users, self.config = formats, users, config

    def _default_id(self, username: str) -> str:
        return (self.users.get(username) or {}).get("default_format_id", "") or ""

    def _bump(self, username: str, **fields: Any) -> None:
        self.users.update(username, fields, inc={"revs.formats": 1})

    # -- queries ------------------------------------------------------------------
    def list(self, username: str) -> list[dict[str, Any]]:
        default_id = self._default_id(username)
        return [public_format(doc, default_id) for doc in self.formats.list(username)]

    def get(self, username: str, format_id: str) -> dict[str, Any]:
        doc = self.formats.get(username, format_id)
        if doc is None:
            raise NotFoundError(f"Format '{format_id}' not found")
        return public_format(doc, self._default_id(username))

    def default(self, username: str) -> Optional[dict[str, Any]]:
        """The default format, repairing the pointer if it dangles (e.g. after a manual DB edit)."""
        formats = self.formats.list(username)
        if not formats:
            return None
        default_id = self._default_id(username)
        chosen = next((d for d in formats if d["_id"] == default_id), None)
        if chosen is None:
            chosen = formats[0]
            self._bump(username, default_format_id=chosen["_id"])
        return public_format(chosen, chosen["_id"])

    def revision(self, username: str) -> int:
        return int(((self.users.get(username) or {}).get("revs") or {}).get("formats", 0))

    def sample(self, username: str, format_id: str) -> bytes:
        data = self.formats.file(username, format_id)
        if data is None:
            raise NotFoundError(f"Format '{format_id}' not found")
        return data

    # -- commands -----------------------------------------------------------------
    def add(self, username: str, name: str, data: bytes) -> dict[str, Any]:
        """Analyse an uploaded ``.docx`` and store it. The user's first format becomes the default."""
        name = (name or "").strip()
        if not name:
            raise ValidationFailed("Format name is required")
        if len(data) > self.config.max_upload_bytes:
            raise ValidationFailed(f"The document is larger than {self.config.max_upload_mb} MB")
        try:
            info, defaults = analyze_sample(data)
        except FormatError as exc:
            raise ValidationFailed(str(exc)) from exc
        stored, sanitized = sanitize_sample(data)  # the stored sample holds no personal text
        if not sanitized:
            info["warnings"] = [*info.get("warnings", []),
                                "The personal text in this sample could not be removed automatically; the original is stored."]
        format_id = f"{_slug(name)}-{uuid.uuid4().hex[:8]}"
        first = not self.formats.list(username)
        doc = {
            "_id": format_id, "user": username, "name": name, **info,
            "settings_defaults": defaults, "overrides": {}, "settings_rev": 0, "rev": 1,
            "size": len(stored), "sanitized": sanitized, "created_at": now_iso(), "created_ns": time.time_ns(),
        }
        self.formats.insert(doc, stored)
        if first:
            self._bump(username, default_format_id=format_id)
        else:
            self._bump(username)
        return public_format(doc, self._default_id(username))

    def set_default(self, username: str, format_id: str) -> dict[str, Any]:
        doc = self.formats.get(username, format_id)
        if doc is None:
            raise NotFoundError(f"Format '{format_id}' not found")
        self._bump(username, default_format_id=format_id)
        return public_format(doc, format_id)

    def delete(self, username: str, format_id: str) -> None:
        """Delete a format; if it was the default, the oldest remaining one becomes the default."""
        if not self.formats.delete(username, format_id):
            raise NotFoundError(f"Format '{format_id}' not found")
        remaining = self.formats.list(username)
        if self._default_id(username) == format_id:
            self._bump(username, default_format_id=remaining[0]["_id"] if remaining else "")
        else:
            self._bump(username)
