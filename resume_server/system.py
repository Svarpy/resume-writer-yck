"""Application system data in the ``system`` collection (version history and the latest version).

One document, ``_id: "app"``::

    {"_id": "app", "name": "Resume Writer", "current_version": "v3.0.0Beta3", "latest_version": "v3.0.0Beta3",
     "versions": [{"version": "v1.0", "status": "previous", "released_at": "2026-07-14", ...},
                  {"version": "v3.0.0Beta3", "status": "latest", ...}], ...}

``register_app_version`` runs when the server starts: it makes sure every known version is listed, adds
the running version if it is new, and marks the newest one as ``latest`` (older ones as ``previous``).
A server older than a version already recorded never demotes that newer one.
"""

from __future__ import annotations

import re
from typing import Any

from pymongo.database import Database

from resume_core.constants import APP_VERSION, VERSION_HISTORY
from resume_server.db import now_iso

SYSTEM_DOC_ID = "app"
APP_NAME = "Resume Writer"
API_VERSION = "v1"


_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:beta(\d+))?$", re.IGNORECASE)


def version_key(version: str) -> tuple[int, int, int, int, int]:
    """Sortable key; accepts ``v1.0``, ``v3.0.0`` and ``v3.0.0Beta3`` (a beta sorts before its release)."""
    match = _VERSION_RE.match(version.strip())
    if not match:
        return (0, 0, 0, 0, 0)
    major, minor, patch, beta = match.groups()
    return (int(major), int(minor), int(patch or 0), 0 if beta is not None else 1, int(beta or 0))


def _newest(versions: list[dict[str, Any]]) -> str:
    return max(versions, key=lambda entry: version_key(entry["version"]))["version"]


def register_app_version(db: Database, version: str = APP_VERSION,
                         history: tuple[tuple[str, str], ...] = VERSION_HISTORY) -> dict[str, Any]:
    """Create or update the system document and return it."""
    doc = db.system.find_one({"_id": SYSTEM_DOC_ID}) or {"_id": SYSTEM_DOC_ID, "versions": [], "created_at": now_iso()}
    versions: list[dict[str, Any]] = list(doc.get("versions") or [])
    known = {entry["version"] for entry in versions}
    for name, released in (*history, (version, "")):
        if name not in known:
            versions.append({"version": name, "status": "previous", "released_at": released,
                             "registered_at": now_iso()})
            known.add(name)
    versions.sort(key=lambda entry: version_key(entry["version"]))
    latest = _newest(versions)
    for entry in versions:
        entry["status"] = "latest" if entry["version"] == latest else "previous"
    doc.update({
        "name": APP_NAME, "current_version": version, "latest_version": latest, "versions": versions,
        "api_version": API_VERSION, "updated_at": now_iso(),
    })
    db.system.replace_one({"_id": SYSTEM_DOC_ID}, doc, upsert=True)
    return doc


def public_system_info(db: Database) -> dict[str, Any]:
    doc = db.system.find_one({"_id": SYSTEM_DOC_ID}) or {}
    return {k: v for k, v in doc.items() if k != "_id"}
