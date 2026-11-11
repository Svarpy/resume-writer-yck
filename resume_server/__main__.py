"""Run the API: ``python -m resume_server``."""

from __future__ import annotations

import sys

import uvicorn
from pymongo.errors import PyMongoError

from resume_server.api import create_app
from resume_server.config import ConfigError, load_config


def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        sys.exit(f"Configuration error: {exc}")
    try:
        app = create_app(config)
    except PyMongoError as exc:
        sys.exit(f"Cannot connect to MongoDB ({config.mongodb_uri.split('@')[-1]}): {exc}")
    uvicorn.run(app, host=config.api_host, port=config.api_port)


if __name__ == "__main__":
    main()
