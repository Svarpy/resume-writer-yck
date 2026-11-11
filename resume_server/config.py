"""Server configuration, read from environment variables (and a ``.env`` file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import find_dotenv, load_dotenv

PLACEHOLDER_SECRET = "change-me-to-a-long-random-string"


class ConfigError(RuntimeError):
    """A required setting is missing or still has its placeholder value."""


@dataclass(frozen=True)
class ServerConfig:
    mongodb_uri: str
    mongodb_db: str = "resume-writer"
    jwt_secret: str = ""
    jwt_expire_hours: int = 168
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    max_upload_mb: int = 10

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def load_config(env_file: Optional[str] = None) -> ServerConfig:
    """Load ``.env`` (``RW_ENV_FILE`` or the nearest one) and build the config, validating secrets."""
    path = env_file or os.environ.get("RW_ENV_FILE") or find_dotenv(usecwd=True)
    if path and Path(path).is_file():
        load_dotenv(path, override=False)
    uri = os.environ.get("MONGODB_URI", "").strip()
    secret = os.environ.get("JWT_SECRET", "").strip()
    if not uri:
        raise ConfigError("MONGODB_URI is not set. Copy .env.example to .env and fill it in.")
    if not secret or secret == PLACEHOLDER_SECRET or len(secret) < 24:
        raise ConfigError("JWT_SECRET must be set to a long random value (at least 24 characters) in .env.")
    return ServerConfig(
        mongodb_uri=uri,
        mongodb_db=os.environ.get("MONGODB_DB", "resume-writer").strip() or "resume-writer",
        jwt_secret=secret,
        jwt_expire_hours=int(os.environ.get("JWT_EXPIRE_HOURS", "168")),
        api_host=os.environ.get("API_HOST", "127.0.0.1"),
        api_port=int(os.environ.get("API_PORT", "8765")),
        max_upload_mb=int(os.environ.get("MAX_UPLOAD_MB", "10")),
    )
