"""``ResumeClient``: one object for the desktop app and the MCP server to use.

Handles sign-in, the API calls and the local cache (settings and default format are cached on disk so
they are not fetched on every use; see ``cache.py`` for how changes invalidate them).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import httpx

from resume_client.cache import DiskCache
from resume_client.config import ClientConfig
from resume_client.errors import AuthRequired, ClientError
from resume_client.http import ApiHttp
from resume_core.backup import backup_basename
from resume_core.settings import Settings


@dataclass
class SettingsView:
    format_id: str
    values: dict[str, Any]
    defaults: dict[str, Any]
    user_rev: int
    format_rev: int

    def settings(self) -> Settings:
        return Settings(self.values, defaults=self.defaults)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SettingsView":
        return cls(data["format_id"], data["values"], data["defaults"], int(data["user_rev"]), int(data["format_rev"]))

    def to_dict(self) -> dict[str, Any]:
        return {"format_id": self.format_id, "values": self.values, "defaults": self.defaults,
                "user_rev": self.user_rev, "format_rev": self.format_rev}


class ResumeClient:
    def __init__(self, config: ClientConfig, http: Optional[httpx.Client] = None) -> None:
        self.config = config
        self.token = config.api_token
        self.username = ""
        self.profile_data: dict[str, Any] = {}
        self._api = ApiHttp(config.api_url, lambda: self.token, http)
        self._cache: Optional[DiskCache] = None

    # ------------------------------------------------------------------ session
    @property
    def signed_in(self) -> bool:
        return bool(self.token and self.username)

    def _start_session(self, token: str, profile: dict[str, Any]) -> dict[str, Any]:
        self.token, self.profile_data, self.username = token, profile, profile["username"]
        self._cache = DiskCache(self.config.root, self.config.api_url, self.username, self.config.cache_ttl)
        return profile

    def login(self, username: str, password: str) -> dict[str, Any]:
        data = self._api.json("POST", "/auth/login", json={"username": username, "password": password})
        return self._start_session(data["token"], data["profile"])

    def signup(self, username: str, password: str, display_name: str = "", email: str = "") -> dict[str, Any]:
        data = self._api.json("POST", "/auth/signup", json={
            "username": username, "password": password, "display_name": display_name, "email": email})
        return self._start_session(data["token"], data["profile"])

    def use_access_token(self, token: str = "") -> dict[str, Any]:
        """Sign in with a personal access token (the MCP server). The username is remembered locally."""
        self.token = token or self.config.api_token
        if not self.token:
            raise AuthRequired("No access token configured. Set RW_API_TOKEN (create one in the desktop app: Profile).")
        identities_path = self.config.root / "cache" / "identities.json"
        key = hashlib.sha256((self.config.api_url + self.token).encode("utf-8")).hexdigest()[:20]
        try:
            known = json.loads(identities_path.read_text(encoding="utf-8")).get(key)
        except (OSError, ValueError):
            known = None
        if known:
            return self._start_session(self.token, {"username": known})
        profile = self._api.json("GET", "/profile")
        try:
            data = json.loads(identities_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data[key] = profile["username"]
        identities_path.parent.mkdir(parents=True, exist_ok=True)
        identities_path.write_text(json.dumps(data), encoding="utf-8")
        return self._start_session(self.token, profile)

    def logout(self) -> None:
        self.token, self.username, self.profile_data, self._cache = "", "", {}, None

    @property
    def cache(self) -> DiskCache:
        if self._cache is None:
            raise AuthRequired("Not signed in")
        return self._cache

    # ------------------------------------------------------------------ account
    @property
    def is_admin(self) -> bool:
        """True when the account's role is ``admin`` (as of the last profile read)."""
        return self.profile_data.get("role") == "admin"

    def profile(self) -> dict[str, Any]:
        self.profile_data = self._api.json("GET", "/profile")
        return self.profile_data

    def update_profile(self, display_name: Optional[str] = None, email: Optional[str] = None) -> dict[str, Any]:
        self.profile_data = self._api.json("PATCH", "/profile", json={"display_name": display_name, "email": email})
        return self.profile_data

    def change_password(self, old: str, new: str) -> None:
        self._api.request("POST", "/auth/password", json={"old_password": old, "new_password": new})

    def list_tokens(self) -> list[dict[str, Any]]:
        return self._api.json("GET", "/tokens")

    def create_token(self, name: str) -> dict[str, Any]:
        return self._api.json("POST", "/tokens", json={"name": name})

    def revoke_token(self, token_id: str) -> None:
        self._api.request("DELETE", f"/tokens/{token_id}")

    # ------------------------------------------------------------------ backup
    def backup_info(self) -> dict[str, Any]:
        """``{"database", "collections": [{"name", "documents"}]}``; administrators only (others get an error)."""
        return self._api.json("GET", "/backup/info")

    def download_backup(self, folder: Path, day: Optional[date] = None) -> Path:
        """Download the backup zip into ``folder`` as ``ResWritBkpYYYYMMMDD.zip`` (never overwrites an existing file)."""
        data = self._api.bytes("/backup")
        folder = Path(folder).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        base = backup_basename(day)
        path = folder / f"{base}.zip"
        number = 2
        while path.exists():
            path = folder / f"{base} ({number}).zip"
            number += 1
        path.write_bytes(data)
        return path

    # ------------------------------------------------------------------ cache validation
    def _state(self) -> dict[str, Any]:
        """Server revision numbers; one small request per cache lifetime (``cache_ttl``), none while fresh."""
        entry = self.cache.read_state()
        if entry and self.cache.is_fresh(entry):
            return entry["state"]
        try:
            state = self._api.json("GET", "/state")
        except ClientError:
            if entry:  # server unreachable: keep working from what is cached
                return entry["state"]
            raise
        self.cache.write_state(state)
        return state

    def refresh(self) -> None:
        """Drop trust in the cache so the next read re-checks the server."""
        self.cache.expire()

    # ------------------------------------------------------------------ formats
    def list_formats(self) -> list[dict[str, Any]]:
        return self._api.json("GET", "/formats")

    def add_format(self, name: str, path: Path) -> dict[str, Any]:
        path = Path(path)
        info = self._api.json("POST", "/formats", data={"name": name},
                              files={"file": (path.name, path.read_bytes())})
        self.refresh()
        return info

    def delete_format(self, format_id: str) -> None:
        self._api.request("DELETE", f"/formats/{format_id}")
        self.refresh()

    def set_default_format(self, format_id: str) -> dict[str, Any]:
        info = self._api.json("PUT", "/formats/default", json={"format_id": format_id})
        self.refresh()
        return info

    def default_format(self) -> Optional[dict[str, Any]]:
        """The default format (cached), or None when the user has not uploaded one."""
        state = self._state()
        if not state["default_format_id"]:
            return None
        entry = self.cache.read("default_format")
        if (entry and entry["info"]["id"] == state["default_format_id"]
                and entry["formats_rev"] == state["formats_rev"]):
            return entry["info"]
        info = self._api.json("GET", "/formats/default")
        if not info:
            return None
        self.cache.write("default_format", {"formats_rev": state["formats_rev"], "info": info})
        return info

    def sample_path(self, format_id: str = "") -> Path:
        """Local copy of a format's sample document (downloaded once per revision)."""
        info = self.default_format() if not format_id else self._api.json("GET", f"/formats/{format_id}")
        if not info:
            from resume_client.errors import NoFormatError

            raise NoFormatError("No resume format yet. Upload a sample document first.")
        path = self.cache.sample_path(info["id"], info["rev"])
        if not path.is_file():
            path = self.cache.store_sample(info["id"], info["rev"], self._api.bytes(f"/formats/{info['id']}/sample"))
        return path

    # ------------------------------------------------------------------ settings
    def settings(self, format_id: Optional[str] = None) -> SettingsView:
        """Settings for ``format_id`` (default: the default format). The default format's are cached."""
        state = self._state()
        wanted = state["default_format_id"] if format_id is None else format_id
        cacheable = wanted == state["default_format_id"]
        if cacheable:
            entry = self.cache.read("settings")
            if (entry and entry["format_id"] == wanted and entry["user_rev"] == state["user_settings_rev"]
                    and entry["format_rev"] == state["format_settings_rev"]):
                return SettingsView.from_api(entry)
        view = SettingsView.from_api(self._api.json("GET", "/settings", params={"format_id": wanted}))
        if cacheable:
            self.cache.write("settings", view.to_dict())
        return view

    def update_settings(self, changes: dict[str, Any], format_id: Optional[str] = None) -> SettingsView:
        wanted = self._format_id_or_default(format_id)
        view = SettingsView.from_api(self._api.json("PATCH", "/settings", json={"format_id": wanted, "changes": changes}))
        self._after_settings_write(view)
        return view

    def reset_settings(self, keys: Optional[list[str]] = None, format_id: Optional[str] = None) -> SettingsView:
        wanted = self._format_id_or_default(format_id)
        view = SettingsView.from_api(self._api.json("POST", "/settings/reset", json={"format_id": wanted, "keys": keys}))
        self._after_settings_write(view)
        return view

    def _format_id_or_default(self, format_id: Optional[str]) -> str:
        if format_id is not None:
            return format_id
        return self._state()["default_format_id"]

    def _after_settings_write(self, view: SettingsView) -> None:
        state = (self.cache.read_state() or {}).get("state") or {}
        if view.format_id == state.get("default_format_id", ""):
            self.cache.write("settings", view.to_dict())  # replaces the older entry
        self.refresh()  # other processes re-check the revisions on their next read
