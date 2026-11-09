"""Local data-directory helpers for ResumeWriter.

All auth profiles and per-user format XML files live under a user-scoped
application data directory (never inside the repo or install bundle).
"""

from __future__ import annotations

import os
from pathlib import Path


APP_DIR_NAME = "ResumeWriter"
ENV_DATA_DIR = "RESUME_WRITER_DATA_DIR"


def get_data_root() -> Path:
    """Return the writable application data root, creating it if needed.

    Override with environment variable ``RESUME_WRITER_DATA_DIR`` (useful for
    tests and isolated runs).
    """
    override = os.environ.get(ENV_DATA_DIR, "").strip()
    if override:
        root = Path(override).expanduser().resolve()
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        root = base / APP_DIR_NAME
    else:
        # macOS / Linux: ~/.ResumeWriter
        root = Path.home() / f".{APP_DIR_NAME}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def users_root() -> Path:
    path = get_data_root() / "users"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_dir(username: str) -> Path:
    safe = sanitize_username(username)
    path = users_root() / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_profile_path(username: str) -> Path:
    return user_dir(username) / "profile.json"


def user_formats_dir(username: str) -> Path:
    path = user_dir(username) / "formats"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_username(username: str) -> str:
    """Normalize a username for filesystem use (case-insensitive identity)."""
    cleaned = "".join(ch for ch in username.strip().lower() if ch.isalnum() or ch in ("_", "-", "."))
    if not cleaned:
        raise ValueError("Username must contain letters, numbers, underscore, dash, or dot")
    return cleaned
