"""Run the desktop app: ``python -m resume_gui`` (add ``--with-server`` to start a local API as well)."""

from __future__ import annotations

import os
import sys
import threading

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")


def _start_local_server() -> None:
    """Run the API in a background thread (needs the server extras and a configured .env)."""
    import uvicorn

    from resume_server.api import create_app
    from resume_server.config import load_config

    config = load_config()
    server = uvicorn.Server(uvicorn.Config(create_app(config), host=config.api_host, port=config.api_port,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()


def main() -> None:
    if "--with-server" in sys.argv:
        try:
            _start_local_server()
        except Exception as exc:  # noqa: BLE001
            sys.exit(f"Could not start the local server: {exc}")
    from resume_gui.app import ResumeWriterApp

    ResumeWriterApp().mainloop()


if __name__ == "__main__":
    main()
