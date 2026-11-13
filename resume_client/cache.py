"""Local disk cache shared by every process of one user on this machine (desktop app, MCP server).

Layout: ``<root>/cache/<server>/<username>/``: ``state.json``, ``default_format.json``,
``settings.json`` and ``samples/<format id>-<rev>.docx``.

Entries remember the server revision numbers they were built from. The server's tiny ``/state``
call returns the current revisions; an entry is used only while its revisions match, so any change
(from this or another process, or another machine) makes the old entry unusable and it is replaced.
Writes are atomic, and every process reads the files directly, so a change made by one process is
seen by the others immediately.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text) or "x"


class DiskCache:
    def __init__(self, root: Path, server: str, username: str, ttl: float, clock: Callable[[], float] = time.time) -> None:
        self.ttl = ttl
        self.clock = clock
        server_key = hashlib.sha256(server.encode("utf-8")).hexdigest()[:10]
        self.dir = root / "cache" / server_key / _safe(username)
        self.dir.mkdir(parents=True, exist_ok=True)

    # -- JSON entries ----------------------------------------------------------------
    def read(self, name: str) -> Optional[Any]:
        try:
            return json.loads((self.dir / f"{name}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write(self, name: str, data: Any) -> None:
        path = self.dir / f"{name}.json"
        temp = path.with_name(path.name + f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, path)

    def delete(self, name: str) -> None:
        (self.dir / f"{name}.json").unlink(missing_ok=True)

    # -- state (revision snapshot + when it was checked) ------------------------------------
    def read_state(self) -> Optional[dict[str, Any]]:
        return self.read("state")

    def write_state(self, state: dict[str, Any], *, checked: bool = True) -> None:
        """Save the server's revision snapshot. ``checked=False`` forces the next read to re-check."""
        self.write("state", {"checked_at": self.clock() if checked else 0.0, "state": state})

    def is_fresh(self, entry: Optional[dict[str, Any]]) -> bool:
        return bool(entry) and (self.clock() - float(entry.get("checked_at", 0))) < self.ttl

    def expire(self) -> None:
        """Make every process re-check the server on its next read (keeps the data for offline use)."""
        entry = self.read_state()
        if entry:
            self.write_state(entry["state"], checked=False)

    def clear(self) -> None:
        for path in self.dir.glob("*.json"):
            path.unlink(missing_ok=True)
        for path in (self.dir / "samples").glob("*.docx") if (self.dir / "samples").is_dir() else []:
            path.unlink(missing_ok=True)

    # -- sample documents ---------------------------------------------------------------------
    def sample_path(self, format_id: str, rev: int) -> Path:
        return self.dir / "samples" / f"{_safe(format_id)}-{rev}.docx"

    def store_sample(self, format_id: str, rev: int, data: bytes) -> Path:
        path = self.sample_path(format_id, rev)
        path.parent.mkdir(parents=True, exist_ok=True)
        for old in path.parent.glob(f"{_safe(format_id)}-*.docx"):  # older revisions are now invalid
            if old != path:
                old.unlink(missing_ok=True)
        temp = path.with_name(path.name + f".{os.getpid()}.tmp")
        temp.write_bytes(data)
        os.replace(temp, path)
        return path
