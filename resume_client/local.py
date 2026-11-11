"""Small local conveniences for the desktop app: the remembered username (never the password)."""

from __future__ import annotations

import json
from pathlib import Path


def remember_username(root: Path, username: str) -> None:
    try:
        (root / "last_user.json").write_text(json.dumps({"username": username.strip()}), encoding="utf-8")
    except OSError:
        pass


def last_username(root: Path) -> str:
    try:
        return str(json.loads((root / "last_user.json").read_text(encoding="utf-8")).get("username", ""))
    except (OSError, ValueError, AttributeError):
        return ""
