"""Client configuration: environment variables / ``.env`` (shared with the server's ``.env``)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import find_dotenv, load_dotenv

APP_DIR_NAME = "ResumeWriter"


def default_data_root() -> Path:
    """Per-user writable folder for the cache and local state (override with ``RW_DATA_DIR``)."""
    override = os.environ.get("RW_DATA_DIR", "").strip()
    if override:
        root = Path(override).expanduser()
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_DIR_NAME
    else:
        root = Path.home() / f".{APP_DIR_NAME}"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass(frozen=True)
class ClientConfig:
    api_url: str = "http://127.0.0.1:8765"
    api_token: str = ""
    cache_ttl: float = 900.0
    data_root: Optional[Path] = None

    @property
    def root(self) -> Path:
        return self.data_root or default_data_root()


def load_client_config(env_file: Optional[str] = None) -> ClientConfig:
    path = env_file or os.environ.get("RW_ENV_FILE") or find_dotenv(usecwd=True)
    if path and Path(path).is_file():
        load_dotenv(path, override=False)
    return ClientConfig(
        api_url=os.environ.get("RW_API_URL", "http://127.0.0.1:8765").strip().rstrip("/"),
        api_token=os.environ.get("RW_API_TOKEN", "").strip(),
        cache_ttl=float(os.environ.get("RW_CACHE_TTL", "900") or 900),
    )
