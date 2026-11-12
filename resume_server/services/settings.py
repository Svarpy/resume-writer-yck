"""Settings service: effective settings per user and format, validated by ``resume_core``.

Only *overrides* are stored (values that differ from their defaults). A setting's default is the
schema default, or - for format-scoped settings - the default derived from the format's template.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Optional

from resume_core.settings import FORMAT_SCOPED_KEYS, SETTING_DEFS_BY_KEY, Settings, SettingsError
from resume_core.settings.schema import STORED_DEFS
from resume_server.db import FormatRepo, SettingsRepo, UserRepo
from resume_server.errors import NotFoundError, ValidationFailed


class SettingsService:
    def __init__(self, settings: SettingsRepo, formats: FormatRepo, users: UserRepo) -> None:
        self.settings, self.formats, self.users = settings, formats, users

    # -- helpers --------------------------------------------------------------
    def _format_doc(self, username: str, format_id: str) -> Optional[dict[str, Any]]:
        if not format_id:
            return None
        doc = self.formats.get(username, format_id)
        if doc is None:
            raise NotFoundError(f"Format '{format_id}' not found")
        return doc

    def _defaults(self, format_doc: Optional[dict[str, Any]]) -> dict[str, Any]:
        defaults = {d.key: copy.deepcopy(d.default) for d in STORED_DEFS}
        if format_doc:
            for key, value in (format_doc.get("settings_defaults") or {}).items():
                if key in FORMAT_SCOPED_KEYS:
                    defaults[key] = copy.deepcopy(value)
        return defaults

    def _build(self, username: str, format_doc: Optional[dict[str, Any]]) -> tuple[Settings, int, int]:
        user_doc = self.settings.get(username)
        overrides = dict(user_doc.get("overrides") or {})
        format_rev = 0
        if format_doc:
            overrides.update(format_doc.get("overrides") or {})
            format_rev = int(format_doc.get("settings_rev", 0))
        settings = Settings(
            {k: v for k, v in overrides.items() if k in SETTING_DEFS_BY_KEY},
            defaults=self._defaults(format_doc),
        )
        return settings, int(user_doc.get("rev", 0)), format_rev

    def _view(self, settings: Settings, format_id: str, user_rev: int, format_rev: int) -> dict[str, Any]:
        return {
            "format_id": format_id,
            "values": settings.all(),
            "defaults": settings.all_defaults(),
            "user_rev": user_rev,
            "format_rev": format_rev,
        }

    def _save(self, username: str, format_doc: Optional[dict[str, Any]], settings: Settings) -> tuple[int, int]:
        changed = {k: v for k, v in settings.all().items() if not settings.is_default(k)}
        user_over = {k: v for k, v in changed.items() if k not in FORMAT_SCOPED_KEYS}
        user_rev = self.settings.set_overrides(username, user_over)
        format_rev = 0
        if format_doc:
            fmt_over = {k: v for k, v in changed.items() if k in FORMAT_SCOPED_KEYS}
            format_rev = self.formats.set_format_overrides(format_doc["_id"], fmt_over)
        return user_rev, format_rev

    # -- public API -----------------------------------------------------------------
    def get(self, username: str, format_id: str = "") -> dict[str, Any]:
        format_doc = self._format_doc(username, format_id)
        settings, user_rev, format_rev = self._build(username, format_doc)
        return self._view(settings, format_id, user_rev, format_rev)

    def update(self, username: str, format_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Apply ``{dotted.key: value}`` changes atomically (all valid, or nothing is saved)."""
        format_doc = self._format_doc(username, format_id)
        settings, user_rev, format_rev = self._build(username, format_doc)
        try:
            for key, value in changes.items():
                if key in FORMAT_SCOPED_KEYS and not format_doc:
                    raise SettingsError(f"'{key}' belongs to a resume format; upload a format first")
                settings.set(key, value)
        except SettingsError as exc:
            raise ValidationFailed(str(exc)) from exc
        user_rev, format_rev = self._save(username, format_doc, settings)
        return self._view(settings, format_id, user_rev, format_rev)

    def reset(self, username: str, format_id: str, keys: Optional[Iterable[str]] = None) -> dict[str, Any]:
        """Reset the given settings (or all of them) to their defaults."""
        format_doc = self._format_doc(username, format_id)
        settings, _u, _f = self._build(username, format_doc)
        if keys is None:
            settings.reset_all()
        else:
            for key in keys:
                if key not in SETTING_DEFS_BY_KEY:
                    raise ValidationFailed(f"Unknown setting '{key}'")
                settings.reset(key)
        user_rev, format_rev = self._save(username, format_doc, settings)
        return self._view(settings, format_id, user_rev, format_rev)

    def seed_user(self, username: str, values: dict[str, Any]) -> None:
        """First-run values for a new account (resume header name/email)."""
        settings = Settings(defaults={})
        for key, value in values.items():
            if key in SETTING_DEFS_BY_KEY and SETTING_DEFS_BY_KEY[key].scope == "user":
                settings.set(key, value)
        overrides = {k: v for k, v in settings.all().items() if not settings.is_default(k)}
        self.settings.set_overrides(username, overrides)
