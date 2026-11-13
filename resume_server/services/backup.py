"""Database backup (administrators only): a mongodump-style archive in one zip.

The archive holds every collection of the database, ``<db>/<collection>.bson`` plus
``<collection>.metadata.json`` (indexes), the way ``mongodump`` writes them. Because that includes every
user's data and password hashes, only accounts whose ``role`` is ``admin`` may create one; everyone else
gets a plain ``404 Not Found``, exactly as for an address that does not exist. The role is
set by hand in the ``users`` collection and is checked in the database on every request.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

import bson
from bson import json_util
from pymongo.database import Database

from resume_core.constants import APP_VERSION
from resume_server.db import ADMIN_ROLE, COLLECTIONS, UserRepo
from resume_server.errors import NotFoundError

README = """Resume Writer backup
====================
Created: {created}
Created by: {user}
App version: {version}
Database: {database} ({documents} documents in {collections} collections)

Each collection is stored the way `mongodump` does: <db>/<collection>.bson and <collection>.metadata.json.
Unzip this file, then restore everything with:

    mongorestore --db {database} <unzipped folder>/{database}

See manifest.json for the document counts.
"""


class BackupService:
    def __init__(self, db: Database, users: UserRepo) -> None:
        self.db, self.users = db, users

    def is_admin(self, username: str) -> bool:
        return self.users.role(username) == ADMIN_ROLE

    def require_admin(self, username: str) -> None:
        if not self.is_admin(username):
            # Not "forbidden": to anyone who is not an administrator the endpoint simply does not exist.
            raise NotFoundError("Not Found")

    def _collection_names(self) -> list[str]:
        existing = [n for n in self.db.list_collection_names() if not n.startswith("system.")]
        return [*COLLECTIONS, *sorted(set(existing) - set(COLLECTIONS))]

    def info(self, username: str) -> dict[str, Any]:
        self.require_admin(username)
        return {"database": self.db.name, "collections": [
            {"name": name, "documents": self.db[name].count_documents({})} for name in self._collection_names()]}

    def _indexes(self, collection: str) -> list[dict[str, Any]]:
        out = []
        for name, spec in self.db[collection].index_information().items():
            entry: dict[str, Any] = {"v": 2, "key": {field: direction for field, direction in spec["key"]}, "name": name}
            if spec.get("unique"):
                entry["unique"] = True
            out.append(entry)
        return out

    def create(self, username: str) -> bytes:
        self.require_admin(username)
        buffer = io.BytesIO()
        manifest: dict[str, Any] = {
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "created_by": username,
            "database": self.db.name, "app_version": APP_VERSION, "collections": {},
        }
        total = 0
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in self._collection_names():
                docs = list(self.db[name].find({}))
                total += len(docs)
                manifest["collections"][name] = len(docs)
                archive.writestr(f"{self.db.name}/{name}.bson", b"".join(bson.encode(doc) for doc in docs))
                archive.writestr(f"{self.db.name}/{name}.metadata.json",
                                 json_util.dumps({"options": {}, "indexes": self._indexes(name)}, indent=2))
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.writestr("README.txt", README.format(
                created=manifest["created_at"], user=username, version=APP_VERSION, database=self.db.name,
                documents=total, collections=len(manifest["collections"])))
        return buffer.getvalue()
