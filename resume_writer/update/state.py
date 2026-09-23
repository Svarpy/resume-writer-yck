"""Persist last update-check timestamp under the user data directory."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from resume_writer.paths import get_data_root

CHECK_INTERVAL_DAYS = 7
STATE_FILENAME = "update_state.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def state_path() -> Path:
    return get_data_root() / STATE_FILENAME


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(state, indent=2, sort_keys=True)
    tmp.write_text(payload + "\n", encoding="utf-8")
    tmp.replace(path)


def parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def last_check_at(state: Optional[dict[str, Any]] = None) -> Optional[datetime]:
    data = load_state() if state is None else state
    return parse_iso_timestamp(data.get("last_check_at"))


def record_check_now(*, when: Optional[datetime] = None) -> datetime:
    """Record that an update check completed (or user chose Remind Later)."""
    stamp = (when or _utc_now()).astimezone(timezone.utc)
    state = load_state()
    state["last_check_at"] = stamp.isoformat().replace("+00:00", "Z")
    save_state(state)
    return stamp


def is_check_due(
    *,
    now: Optional[datetime] = None,
    interval_days: int = CHECK_INTERVAL_DAYS,
    state: Optional[dict[str, Any]] = None,
) -> bool:
    """True when no prior check exists or the weekly interval has elapsed."""
    current = (now or _utc_now()).astimezone(timezone.utc)
    previous = last_check_at(state)
    if previous is None:
        return True
    return current >= previous + timedelta(days=interval_days)
