"""API + services against an in-memory MongoDB (mongomock)."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import unittest
from pathlib import Path

import mongomock
from fastapi.testclient import TestClient

from resume_server.api import create_app
from resume_server.config import ServerConfig

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "formats"
CONFIG = ServerConfig(mongodb_uri="mongomock://", jwt_secret="x" * 40, max_upload_mb=2)


def make_client() -> TestClient:
    return TestClient(create_app(CONFIG, mongomock.MongoClient()["resume_test"]))


def signup(client: TestClient, username="alice", password="Passw0rd1", **extra) -> dict:
    response = client.post("/api/v1/auth/signup", json={"username": username, "password": password, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def upload(client: TestClient, token: str, name: str, fixture: str = "YcKResume.docx"):
    data = (FIXTURES / fixture).read_bytes()
    return client.post("/api/v1/formats", headers=auth(token), data={"name": name}, files={"file": (fixture, data)})


class ApiDocumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client()

    def test_swagger_and_redoc_are_served(self) -> None:
        docs = self.client.get("/docs")
        self.assertEqual(docs.status_code, 200)
        self.assertIn("swagger-ui", docs.text.lower())
        self.assertEqual(self.client.get("/redoc").status_code, 200)
        self.assertEqual(self.client.get("/openapi.json").status_code, 200)

    def test_documentation_explains_authentication_and_groups_endpoints(self) -> None:
        spec = self.client.get("/openapi.json").json()
        scheme = spec["components"]["securitySchemes"]["HTTPBearer"]  # gives Swagger its "Authorize" button
        self.assertEqual((scheme["type"], scheme["scheme"]), ("http", "bearer"))
        self.assertIn("Profile > Access Tokens", scheme["description"])
        self.assertIn({"HTTPBearer": []}, spec["paths"]["/api/v1/formats"]["get"]["security"])
        self.assertNotIn("security", spec["paths"]["/api/v1/auth/login"]["post"])  # login needs no token
        tags = {t["name"] for t in spec["tags"]}
        self.assertEqual(tags, {"Account", "Formats", "Settings", "System", "Cache"})
        for path, methods in spec["paths"].items():
            for operation in methods.values():
                self.assertTrue(operation.get("tags"), path)  # every documented endpoint belongs to a group

    def test_backup_endpoints_are_not_advertised_in_the_documentation(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertFalse([p for p in paths if "backup" in p])

    def test_a_pasted_token_works_exactly_as_swagger_sends_it(self) -> None:
        token = signup(self.client)["token"]
        self.assertEqual(self.client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token}"}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/profile", headers={"Authorization": "Bearer"}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/profile").json()["detail"], "Missing bearer token")


class SystemCollectionTests(unittest.TestCase):
    def test_version_history_is_recorded_with_the_latest_marked(self) -> None:
        from resume_core.constants import APP_VERSION
        from resume_server.system import register_app_version

        db = mongomock.MongoClient()["system_test"]
        client = TestClient(create_app(CONFIG, db))
        doc = db.system.find_one({"_id": "app"})
        self.assertEqual(doc["current_version"], APP_VERSION)
        self.assertEqual(doc["latest_version"], APP_VERSION)
        names = [v["version"] for v in doc["versions"]]
        self.assertEqual(names, ["v1.0", "v1.1", "v2.0", "v2.1", "v3.0.0Beta2", APP_VERSION])
        self.assertEqual([v["version"] for v in doc["versions"] if v["status"] == "latest"], [APP_VERSION])
        self.assertTrue(all(v["status"] == "previous" for v in doc["versions"][:-1]))
        self.assertEqual(doc["versions"][0]["released_at"], "2026-07-14")
        public = client.get("/api/v1/system").json()  # readable without signing in
        self.assertEqual(public["latest_version"], APP_VERSION)
        self.assertNotIn("_id", public)

        again = register_app_version(db)  # restarting changes nothing but the timestamp
        self.assertEqual([v["version"] for v in again["versions"]], names)
        self.assertEqual(db.system.count_documents({}), 1)

        upgraded = register_app_version(db, "v4.0.0")  # a newer release registers itself and becomes the latest
        self.assertEqual(upgraded["latest_version"], "v4.0.0")
        statuses = {v["version"]: v["status"] for v in upgraded["versions"]}
        self.assertEqual(statuses["v4.0.0"], "latest")
        self.assertEqual(statuses[APP_VERSION], "previous")

        older = register_app_version(db, "v2.1")  # an older server never demotes the newer version
        self.assertEqual(older["latest_version"], "v4.0.0")
        self.assertEqual(older["current_version"], "v2.1")
        self.assertEqual(len(older["versions"]), len(names) + 1)

    def test_all_collections_exist_right_after_start_up(self) -> None:
        db = mongomock.MongoClient()["fresh"]
        create_app(CONFIG, db)
        self.assertEqual(set(db.list_collection_names()),
                         {"users", "api_tokens", "formats", "format_files", "settings", "system"})
        client = TestClient(create_app(CONFIG, db))  # starting again is harmless
        signup(client)
        self.assertEqual(db.users.count_documents({}), 1)
        self.assertEqual(client.post("/api/v1/auth/login", json={"username": "alice", "password": "Passw0rd1"}).status_code, 200)

    def test_default_database_name_matches_the_local_database(self) -> None:
        self.assertEqual(ServerConfig(mongodb_uri="x").mongodb_db, "resume-writer")


class AuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client()

    def test_signup_login_profile_and_password_rules(self) -> None:
        created = signup(self.client, display_name="Alice A", email="a@example.com")
        self.assertEqual(created["profile"]["username"], "alice")
        self.assertEqual(self.client.post("/api/v1/auth/signup", json={"username": "ALICE", "password": "Passw0rd1"}).status_code, 409)
        for bad in ("short1", "nodigitsss", "12345678"):
            self.assertEqual(self.client.post("/api/v1/auth/signup", json={"username": "bob", "password": bad}).status_code, 422)
        login = self.client.post("/api/v1/auth/login", json={"username": "Alice", "password": "Passw0rd1"})
        self.assertEqual(login.status_code, 200)
        token = login.json()["token"]
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "nope-nope1"}).status_code, 401)
        profile = self.client.get("/api/v1/profile", headers=auth(token)).json()
        self.assertEqual(profile["display_name"], "Alice A")
        updated = self.client.patch("/api/v1/profile", headers=auth(token), json={"display_name": "New Name"}).json()
        self.assertEqual(updated["display_name"], "New Name")
        wrong = self.client.post("/api/v1/auth/password", headers=auth(token), json={"old_password": "bad", "new_password": "NewPassw0rd"})
        self.assertEqual(wrong.status_code, 401)
        ok = self.client.post("/api/v1/auth/password", headers=auth(token), json={"old_password": "Passw0rd1", "new_password": "NewPassw0rd"})
        self.assertEqual(ok.status_code, 204)
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "NewPassw0rd"}).status_code, 200)

    def test_every_data_endpoint_requires_a_token(self) -> None:
        for method, path in (("get", "/api/v1/profile"), ("get", "/api/v1/formats"), ("get", "/api/v1/settings"),
                             ("get", "/api/v1/state"), ("get", "/api/v1/tokens")):
            self.assertEqual(getattr(self.client, method)(path).status_code, 401, path)
        self.assertEqual(self.client.get("/api/v1/profile", headers=auth("garbage")).status_code, 401)
        self.assertEqual(self.client.get("/health").json()["status"], "ok")

    def test_passwords_are_hashed_in_the_database(self) -> None:
        db = mongomock.MongoClient()["pw"]
        client = TestClient(create_app(CONFIG, db))
        signup(client)
        stored = db.users.find_one({"_id": "alice"})["password_hash"]
        self.assertNotIn("Passw0rd1", stored)
        self.assertTrue(stored.startswith("$2"))

    def test_personal_access_tokens(self) -> None:
        token = signup(self.client)["token"]
        created = self.client.post("/api/v1/tokens", headers=auth(token), json={"name": "claude"}).json()
        pat = created["token"]
        self.assertTrue(pat.startswith("rwt_"))
        self.assertEqual(self.client.get("/api/v1/profile", headers=auth(pat)).json()["username"], "alice")
        listed = self.client.get("/api/v1/tokens", headers=auth(token)).json()
        self.assertEqual([t["name"] for t in listed], ["claude"])
        self.assertNotIn("token", listed[0])  # the secret is only shown once
        self.assertEqual(self.client.delete(f"/api/v1/tokens/{created['id']}", headers=auth(token)).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/profile", headers=auth(pat)).status_code, 401)

    def test_users_cannot_see_each_others_data(self) -> None:
        alice = signup(self.client, "alice")["token"]
        bob = signup(self.client, "bobby")["token"]
        fmt = upload(self.client, alice, "Mine").json()
        self.assertEqual(self.client.get(f"/api/v1/formats/{fmt['id']}", headers=auth(bob)).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/formats/{fmt['id']}/sample", headers=auth(bob)).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/formats/{fmt['id']}", headers=auth(bob)).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/formats", headers=auth(bob)).json(), [])


class FormatApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client()
        self.token = signup(self.client)["token"]

    def test_first_upload_is_default_and_default_can_change(self) -> None:
        self.assertEqual(self.client.get("/api/v1/formats/default", headers=auth(self.token)).json(), {})
        first = upload(self.client, self.token, "First").json()
        second = upload(self.client, self.token, "Second", "YcKResumeFTR2.docx").json()
        self.assertTrue(first["is_default"])
        self.assertFalse(second["is_default"])
        self.assertEqual([s["key"] for s in first["sections"]], ["summary", "skills", "experience", "education"])
        self.assertEqual(first["font_name"], "Arial")
        default = self.client.get("/api/v1/formats/default", headers=auth(self.token)).json()
        self.assertEqual(default["id"], first["id"])
        changed = self.client.put("/api/v1/formats/default", headers=auth(self.token), json={"format_id": second["id"]})
        self.assertEqual(changed.status_code, 200)
        listed = self.client.get("/api/v1/formats", headers=auth(self.token)).json()
        self.assertEqual({f["id"]: f["is_default"] for f in listed}, {first["id"]: False, second["id"]: True})
        self.assertEqual(self.client.put("/api/v1/formats/default", headers=auth(self.token), json={"format_id": "nope"}).status_code, 404)

    def test_delete_promotes_next_and_last_delete_leaves_none(self) -> None:
        first = upload(self.client, self.token, "First").json()
        second = upload(self.client, self.token, "Second", "YcKResumeFTR2.docx").json()
        self.assertEqual(self.client.delete(f"/api/v1/formats/{first['id']}", headers=auth(self.token)).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/formats/default", headers=auth(self.token)).json()["id"], second["id"])
        self.client.delete(f"/api/v1/formats/{second['id']}", headers=auth(self.token))
        self.assertEqual(self.client.get("/api/v1/formats/default", headers=auth(self.token)).json(), {})
        self.assertEqual(self.client.get(f"/api/v1/formats/{second['id']}", headers=auth(self.token)).status_code, 404)

    def test_sample_download_roundtrip_and_upload_validation(self) -> None:
        fmt = upload(self.client, self.token, "Ref").json()
        sample = self.client.get(f"/api/v1/formats/{fmt['id']}/sample", headers=auth(self.token))
        self.assertTrue(fmt["sanitized"])
        self.assertNotEqual(sample.content, (FIXTURES / "YcKResume.docx").read_bytes())  # personal text removed...
        self.assertNotIn(b"Yashashchandra", sample.content)
        from resume_core.formats import analyze_sample

        self.assertEqual(analyze_sample(sample.content)[0]["sections"], fmt["sections"])  # ...same format
        self.assertTrue(sample.content.startswith(b"PK"))
        bad = self.client.post("/api/v1/formats", headers=auth(self.token), data={"name": "Bad"},
                               files={"file": ("x.docx", b"not a word document")})
        self.assertEqual(bad.status_code, 422)
        blank = self.client.post("/api/v1/formats", headers=auth(self.token), data={"name": "  "},
                                 files={"file": ("x.docx", (FIXTURES / "YcKResume.docx").read_bytes())})
        self.assertEqual(blank.status_code, 422)
        huge = self.client.post("/api/v1/formats", headers=auth(self.token), data={"name": "Huge"},
                                files={"file": ("x.docx", b"PK" + b"0" * (3 * 1024 * 1024))})
        self.assertEqual(huge.status_code, 422)


class BackupApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = mongomock.MongoClient()["backup_test"]
        self.client = TestClient(create_app(CONFIG, self.db))
        self.boss = signup(self.client, "boss")["token"]
        self.alice = signup(self.client, "alice")["token"]
        self.make_admin("boss")  # done by hand in the database, as in real use
        upload(self.client, self.alice, "Alice Format")
        upload(self.client, self.boss, "Boss Format", "YcKResumeFTR2.docx")
        self.client.patch("/api/v1/settings", headers=auth(self.alice), json={"changes": {"personal.phone": "ALICE-PHONE"}})

    def make_admin(self, username: str, role: str = "admin") -> None:
        self.db.users.update_one({"_id": username}, {"$set": {"role": role}})

    def archive(self, token: str):
        import io
        import zipfile

        response = self.client.get("/api/v1/backup", headers=auth(token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        return response, zipfile.ZipFile(io.BytesIO(response.content))

    @staticmethod
    def documents(archive, collection: str) -> list[dict]:
        import bson

        return bson.decode_all(archive.read(f"backup_test/{collection}.bson"))

    def test_every_new_user_has_the_default_role_user(self) -> None:
        self.assertEqual(self.db.users.find_one({"_id": "alice"})["role"], "user")
        self.assertEqual(self.client.get("/api/v1/profile", headers=auth(self.alice)).json()["role"], "user")
        self.assertEqual(self.client.get("/api/v1/profile", headers=auth(self.boss)).json()["role"], "admin")
        login = self.client.post("/api/v1/auth/login", json={"username": "alice", "password": "Passw0rd1"}).json()
        self.assertEqual(login["profile"]["role"], "user")

    def test_accounts_created_before_roles_existed_get_the_default_role_at_start_up(self) -> None:
        db = mongomock.MongoClient()["legacy"]
        db.users.insert_one({"_id": "old", "password_hash": "x", "display_name": "Old"})
        db.users.insert_one({"_id": "kept", "password_hash": "x", "role": "admin"})
        create_app(CONFIG, db)
        self.assertEqual(db.users.find_one({"_id": "old"})["role"], "user")
        self.assertEqual(db.users.find_one({"_id": "kept"})["role"], "admin")  # existing roles are never touched

    def test_only_admins_can_back_up_everyone_else_sees_a_plain_404(self) -> None:
        unknown = self.client.get("/api/v1/does-not-exist", headers=auth(self.alice))
        for path in ("/api/v1/backup", "/api/v1/backup/info"):
            denied = self.client.get(path, headers=auth(self.alice))
            self.assertEqual(denied.status_code, 404, path)  # not 403: the endpoint does not exist for them
            self.assertEqual(denied.json(), unknown.json(), path)  # and the answer is identical to a missing address
            self.assertEqual(self.client.get(path).status_code, 401)  # and a token is needed at all
            self.assertEqual(self.client.get(path, headers=auth(self.boss)).status_code, 200)

    def test_the_role_is_checked_in_the_database_on_every_request(self) -> None:
        self.assertEqual(self.client.get("/api/v1/backup", headers=auth(self.alice)).status_code, 404)
        self.make_admin("alice")  # promoted by hand: the existing login token works at once
        self.assertEqual(self.client.get("/api/v1/backup", headers=auth(self.alice)).status_code, 200)
        self.make_admin("alice", "user")  # demoted again
        self.assertEqual(self.client.get("/api/v1/backup", headers=auth(self.alice)).status_code, 404)
        self.make_admin("alice", "Admin ")  # only the exact role "admin" counts
        self.assertEqual(self.client.get("/api/v1/backup", headers=auth(self.alice)).status_code, 404)

    def test_file_name_and_layout_are_mongodump_style(self) -> None:
        import json

        response, archive = self.archive(self.boss)
        self.assertRegex(response.headers["content-disposition"], r'filename="ResWritBkp\d{4}[A-Z][a-z]{2}\d{2}\.zip"')
        names = set(archive.namelist())
        for collection in ("users", "api_tokens", "formats", "format_files", "settings", "system"):
            self.assertIn(f"backup_test/{collection}.bson", names)
            self.assertIn(f"backup_test/{collection}.metadata.json", names)
        self.assertTrue({"manifest.json", "README.txt"} <= names)
        manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual((manifest["created_by"], manifest["collections"]["users"]), ("boss", 2))
        self.assertIn("mongorestore --db backup_test", archive.read("README.txt").decode())
        metadata = json.loads(archive.read("backup_test/api_tokens.metadata.json"))
        self.assertTrue(any(i["name"] == "hash_1" and i.get("unique") for i in metadata["indexes"]))

    def test_the_backup_is_the_whole_database_and_restorable(self) -> None:
        _response, archive = self.archive(self.boss)
        users = {doc["_id"]: doc for doc in self.documents(archive, "users")}
        self.assertEqual(set(users), {"boss", "alice"})
        self.assertEqual((users["alice"]["role"], users["boss"]["role"]), ("user", "admin"))
        self.assertTrue(users["alice"]["password_hash"].startswith("$2"))  # a restorable backup needs the hashes
        self.assertEqual(len(self.documents(archive, "formats")), 2)
        files = self.documents(archive, "format_files")
        self.assertEqual({f["_id"] for f in files}, {f["_id"] for f in self.db.format_files.find()})
        self.assertEqual(self.documents(archive, "settings"), list(self.db.settings.find({})))
        self.assertEqual(self.documents(archive, "system")[0]["_id"], "app")
        info = self.client.get("/api/v1/backup/info", headers=auth(self.boss)).json()
        self.assertEqual({c["name"]: c["documents"] for c in info["collections"]}["users"], 2)


class SanitizeFallbackTests(unittest.TestCase):
    def test_original_is_kept_with_a_warning_when_sanitising_is_not_possible(self) -> None:
        from unittest import mock

        client = make_client()
        token = signup(client)["token"]
        original = (FIXTURES / "YcKResume.docx").read_bytes()
        with mock.patch("resume_server.services.formats.sanitize_sample", return_value=(original, False)):
            fmt = upload(client, token, "Ref").json()
        self.assertFalse(fmt["sanitized"])
        self.assertTrue(any("could not be removed" in w for w in fmt["warnings"]))
        sample = client.get(f"/api/v1/formats/{fmt['id']}/sample", headers=auth(token)).content
        self.assertEqual(sample, original)  # the upload still works and the format is unchanged


class SettingsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client()
        self.token = signup(self.client, display_name="Alice A", email="a@example.com")["token"]

    def get(self, format_id: str = "") -> dict:
        return self.client.get("/api/v1/settings", headers=auth(self.token), params={"format_id": format_id}).json()

    def patch(self, changes: dict, format_id: str = ""):
        return self.client.patch("/api/v1/settings", headers=auth(self.token), json={"format_id": format_id, "changes": changes})

    def test_defaults_seeded_values_and_validation(self) -> None:
        view = self.get()
        self.assertEqual(view["values"]["personal.name"], "Alice A")
        self.assertEqual(view["values"]["personal.email"], "a@example.com")
        self.assertEqual(view["defaults"]["personal.name"], "")
        updated = self.patch({"personal.phone": " +1 555 ", "appearance.accent_color": "rgb(255, 0, 0)"}).json()
        self.assertEqual(updated["values"]["personal.phone"], "+1 555")
        self.assertEqual(updated["values"]["appearance.accent_color"], "#ff0000")
        bad = self.patch({"output.filename_template": "no-company", "personal.location": "Oslo"})
        self.assertEqual(bad.status_code, 422)
        self.assertIn("{company}", bad.json()["detail"])
        self.assertEqual(self.get()["values"]["personal.location"], "")  # all-or-nothing
        self.assertEqual(self.patch({"nope.key": 1}).status_code, 422)

    def test_overrides_saved_for_removed_settings_are_ignored_and_dropped(self) -> None:
        """Accounts that still hold the old `updates.*` settings keep working; the keys disappear on the next save."""
        db = mongomock.MongoClient()["stale"]
        client = TestClient(create_app(CONFIG, db))
        token = signup(client)["token"]
        db.settings.update_one({"_id": "alice"}, {"$set": {"overrides": {"updates.auto_check": False, "personal.phone": "1"}}}, upsert=True)
        view = client.get("/api/v1/settings", headers=auth(token)).json()
        self.assertNotIn("updates.auto_check", view["values"])
        self.assertEqual(view["values"]["personal.phone"], "1")
        client.patch("/api/v1/settings", headers=auth(token), json={"changes": {"personal.location": "Rome"}})
        self.assertEqual(set(db.settings.find_one({"_id": "alice"})["overrides"]), {"personal.phone", "personal.location"})

    def test_revisions_and_reset(self) -> None:
        before = self.get()["user_rev"]
        self.patch({"personal.phone": "1"})
        self.assertGreater(self.get()["user_rev"], before)
        reset = self.client.post("/api/v1/settings/reset", headers=auth(self.token),
                                 json={"format_id": "", "keys": ["personal.phone"]}).json()
        self.assertEqual(reset["values"]["personal.phone"], "")
        self.patch({"personal.phone": "2", "personal.location": "Oslo"})
        everything = self.client.post("/api/v1/settings/reset", headers=auth(self.token), json={"format_id": ""}).json()
        self.assertEqual(everything["values"]["personal.location"], "")
        self.assertEqual(self.client.post("/api/v1/settings/reset", headers=auth(self.token),
                                          json={"keys": ["missing"]}).status_code, 422)

    def test_format_settings_follow_the_format_and_are_separate(self) -> None:
        one = upload(self.client, self.token, "One").json()
        two = upload(self.client, self.token, "Two", "YcKResumeFTR2.docx").json()
        view_one, view_two = self.get(one["id"]), self.get(two["id"])
        headings = lambda v: [r["heading"] for r in v["values"]["sections.items"]]  # noqa: E731
        self.assertIn("Professional Experience", headings(view_one))
        self.assertIn("WORK EXPERIENCE", headings(view_two))
        self.assertIn(24, view_two["values"]["fonts.name_size_choices"])
        # format-scoped settings need a format; user-wide ones do not
        self.assertEqual(self.patch({"sections.items": []}).status_code, 422)
        rows = view_one["values"]["sections.items"]
        rows[0]["label"] = "About Me"
        self.assertEqual(self.patch({"sections.items": rows, "personal.location": "Rome"}, one["id"]).status_code, 200)
        self.assertEqual(self.get(one["id"])["values"]["sections.items"][0]["label"], "About Me")
        self.assertNotEqual(self.get(two["id"])["values"]["sections.items"][0]["label"], "About Me")
        self.assertEqual(self.get(two["id"])["values"]["personal.location"], "Rome")  # user-wide
        self.client.post("/api/v1/settings/reset", headers=auth(self.token), json={"format_id": one["id"], "keys": ["sections.items"]})
        self.assertNotEqual(self.get(one["id"])["values"]["sections.items"][0]["label"], "About Me")
        self.assertEqual(self.get("missing-id").get("detail"), "Format 'missing-id' not found")

    def test_state_changes_when_anything_cacheable_changes(self) -> None:
        def state() -> dict:
            return self.client.get("/api/v1/state", headers=auth(self.token)).json()

        empty = state()
        self.assertEqual(empty["default_format_id"], "")
        fmt = upload(self.client, self.token, "One").json()
        after_upload = state()
        self.assertEqual(after_upload["default_format_id"], fmt["id"])
        self.assertGreater(after_upload["formats_rev"], empty["formats_rev"])
        self.patch({"personal.phone": "1"})
        self.assertGreater(state()["user_settings_rev"], after_upload["user_settings_rev"])
        before = state()["format_settings_rev"]
        rows = self.get(fmt["id"])["values"]["sections.items"]
        self.patch({"sections.items": rows[:2]}, fmt["id"])
        self.assertGreater(state()["format_settings_rev"], before)


if __name__ == "__main__":
    unittest.main()
