"""ResumeClient (cache + invalidation) and the local generation engine, against the in-memory server."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import tempfile
import unittest
from pathlib import Path

from docx import Document

from resume_client import NoFormatError, ServerUnavailable
from resume_client import engine
from resume_client.errors import ApiError, AuthRequired
from resume_core.ooxml.xmlutil import iter_paragraphs, paragraph_text
from tests.support import FIXTURES, World



class ClientCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = World()
        self.http = self.world.http
        self.client = self.world.login(signup=True)
        self.client.add_format("Ref", FIXTURES / "YcKResume.docx")

    def test_settings_and_default_format_are_cached_between_calls(self) -> None:
        first = self.client.settings()
        self.assertEqual(first.values["personal.name"], "Alice A")
        self.http.calls.clear()
        for _ in range(5):
            self.client.settings()
            self.client.default_format()
            self.client.sample_path()
        # After the first write-through the revisions are re-checked once, then nothing hits the server.
        self.assertLessEqual(len(self.http.calls), 3, self.http.calls)
        self.http.calls.clear()
        for _ in range(5):
            self.client.settings()
            self.client.default_format()
            self.client.sample_path()
        self.assertEqual(self.http.calls, [])

    def test_a_local_change_replaces_the_cache_everywhere(self) -> None:
        mcp = self.world.login()  # a second local process (e.g. the MCP server) sharing the same cache folder
        self.assertEqual(mcp.settings().values["personal.phone"], "")
        self.client.update_settings({"personal.phone": "+1 555 0100"})
        self.assertEqual(mcp.settings().values["personal.phone"], "+1 555 0100")  # no waiting for the TTL
        self.assertEqual(self.client.settings().values["personal.phone"], "+1 555 0100")

    def test_changes_from_elsewhere_are_picked_up_after_the_ttl(self) -> None:
        other_machine = self.world.login(root=Path(tempfile.mkdtemp(prefix="rw-other-")))
        self.client.settings()
        other_machine.update_settings({"personal.location": "Rome"})
        self.assertEqual(self.client.settings().values["personal.location"], "")  # still trusted: within the TTL
        self.world.now[0] += self.world.ttl + 1
        self.http.calls.clear()
        self.assertEqual(self.client.settings().values["personal.location"], "Rome")
        self.assertEqual(self.http.count("/state"), 1)

    def test_unchanged_server_after_ttl_costs_one_small_check_not_a_refetch(self) -> None:
        self.client.settings()
        self.client.default_format()
        self.client.settings()
        self.world.now[0] += self.world.ttl + 1
        self.http.calls.clear()
        self.client.settings()
        self.client.default_format()
        self.assertEqual(self.http.count("GET /api/v1/state"), 1)
        self.assertEqual(self.http.count("/settings"), 0)
        self.assertEqual(self.http.count("/formats"), 0)

    def test_default_format_change_switches_cached_settings_and_sample(self) -> None:
        sections_before = [r["heading"] for r in self.client.settings().values["sections.items"]]
        second = self.client.add_format("Second", FIXTURES / "YcKResumeFTR2.docx")
        self.assertEqual(self.client.default_format()["name"], "Ref")
        sample_before = self.client.sample_path()
        self.client.set_default_format(second["id"])
        self.assertEqual(self.client.default_format()["name"], "Second")
        self.assertNotEqual(self.client.sample_path(), sample_before)
        sections_after = [r["heading"] for r in self.client.settings().values["sections.items"]]
        self.assertNotEqual(sections_before, sections_after)
        self.assertIn("WORK EXPERIENCE", sections_after)
        from resume_core.formats import analyze_sample

        sample = self.client.sample_path().read_bytes()  # the stored (sanitised) sample of the second format
        headings = [s["heading"] for s in analyze_sample(sample)[0]["sections"]]
        self.assertIn("PROFESSIONAL SUMMARY", headings)

    def test_sample_is_downloaded_once_and_replaced_per_revision(self) -> None:
        self.client.sample_path()
        self.http.calls.clear()
        self.client.sample_path()
        self.assertEqual(self.http.count("/sample"), 0)
        self.client.delete_format(self.client.default_format()["id"])
        self.assertIsNone(self.client.default_format())
        with self.assertRaises(NoFormatError):
            self.client.sample_path()

    def test_reset_and_validation_errors_come_back_as_messages(self) -> None:
        self.client.update_settings({"personal.phone": "1"})
        reset = self.client.reset_settings(["personal.phone"])
        self.assertEqual(reset.values["personal.phone"], "")
        with self.assertRaises(ApiError) as caught:
            self.client.update_settings({"output.filename_template": "oops"})
        self.assertIn("{company}", str(caught.exception))
        self.assertEqual(self.client.settings().values["output.filename_template"], "Resume{company}{date}")

    def test_works_offline_from_the_cache_but_not_without_one(self) -> None:
        self.client.settings()
        self.client.sample_path()
        self.client.default_format()
        self.world.now[0] += self.world.ttl + 1  # cache is stale, so the client wants to re-check...
        self.http.down = True  # ...but the server is unreachable
        try:
            self.assertEqual(self.client.settings().values["personal.name"], "Alice A")
            self.assertTrue(self.client.sample_path().is_file())
            with self.assertRaises(ServerUnavailable):
                self.client.update_settings({"personal.phone": "1"})
            empty = self.world.client(Path(tempfile.mkdtemp()))  # a brand new machine has no cache
            empty.token, empty.username = self.client.token, "alice"
            empty._cache = type(self.client.cache)(empty.config.root, empty.config.api_url, "alice", 900)
            with self.assertRaises(ServerUnavailable):
                empty.settings()
        finally:
            self.http.down = False

    def test_access_token_sign_in_remembers_the_user(self) -> None:
        token = self.client.create_token("mcp")["token"]
        mcp = self.world.client()
        profile = mcp.use_access_token(token)
        self.assertEqual(profile["username"], "alice")
        self.assertEqual(mcp.default_format()["name"], "Ref")
        self.http.calls.clear()
        again = self.world.client()
        again.use_access_token(token)
        self.assertEqual(self.http.count("/profile"), 0)  # identity remembered locally
        with self.assertRaises(AuthRequired):
            self.world.client().use_access_token("")
        self.client.revoke_token(self.client.list_tokens()[0]["id"])
        self.world.now[0] += self.world.ttl + 1
        revoked = self.world.client()
        revoked.use_access_token(token)
        revoked.cache.clock = lambda: self.world.now[0]
        with self.assertRaises(AuthRequired):
            revoked.settings()


class ClientBackupTests(unittest.TestCase):
    def test_download_names_the_file_and_never_overwrites(self) -> None:
        import zipfile
        from datetime import date

        world = World()
        client = world.login(signup=True)
        client.add_format("Ref", FIXTURES / "YcKResume.docx")
        self.assertFalse(client.is_admin)
        with self.assertRaises(ApiError) as denied:
            client.download_backup(Path(tempfile.mkdtemp()))
        self.assertEqual(denied.exception.status, 404)  # looks like a missing address, not a refusal
        world.http.app.state.db.users.update_one({"_id": "alice"}, {"$set": {"role": "admin"}})  # promoted by hand
        self.assertFalse(client.is_admin)  # the role is known after the next profile read
        client.profile()
        self.assertTrue(client.is_admin)
        info = client.backup_info()
        self.assertEqual({c["name"]: c["documents"] for c in info["collections"]}["formats"], 1)
        folder = Path(tempfile.mkdtemp(prefix="rw-backup-"))
        first = client.download_backup(folder, day=date(2026, 11, 11))
        second = client.download_backup(folder, day=date(2026, 11, 11))
        self.assertEqual((first.name, second.name), ("ResWritBkp2026Nov11.zip", "ResWritBkp2026Nov11 (2).zip"))
        self.assertIn("manifest.json", zipfile.ZipFile(first).namelist())
        self.assertRegex(client.download_backup(Path(tempfile.mkdtemp(prefix="rw-backup-"))).name, r"^ResWritBkp\d{4}[A-Z][a-z]{2}\d{2}\.zip$")


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = World()
        self.client = self.world.login(signup=True)
        self.out = Path(tempfile.mkdtemp(prefix="rw-out-"))

    def _with_format(self, fixture: str = "YcKResume.docx") -> engine.WriterContext:
        self.client.add_format("Ref", FIXTURES / fixture)
        self.client.update_settings({"output.directory": str(self.out), "personal.email": "a@example.com"})
        return engine.load_context(self.client)

    def test_no_format_means_no_context(self) -> None:
        with self.assertRaises(NoFormatError):
            engine.load_context(self.client)

    def test_generate_writes_the_document_locally(self) -> None:
        ctx = self._with_format()
        texts = {"summary": "A short summary.", "skills": "Languages: Python", "top_skills": "a, b",
                 "experience": "Acme | Remote   May 2020 - Present\n- Built it"}
        path = engine.generate(ctx, texts, "Acme")
        self.assertEqual(path.parent, self.out)
        self.assertTrue(path.name.startswith("ResumeAcme"))
        document = Document(str(path))
        lines = [paragraph_text(p) for p in iter_paragraphs(document.element.body)]
        self.assertEqual(lines[0], "Alice A")
        self.assertIn("Professional Experience", lines)
        self.assertIn("Acme  |  Remote\tMay 2020 – Present", lines)
        self.assertNotIn("Yashashchandra", "\n".join(lines))
        # Same company again is blocked by the duplicate check; switching the check off allows it.
        with self.assertRaises(engine.GenerationError) as caught:
            engine.generate(ctx, texts, "Acme")
        self.assertIn("already exists", str(caught.exception))
        self.client.update_settings({"duplicate_check.enabled": False})
        self.assertTrue(engine.generate(engine.load_context(self.client), texts, "Acme").is_file())

    def test_validation_messages(self) -> None:
        ctx = self._with_format()
        errors = engine.validation_errors(ctx.settings, {}, "", "alice")
        self.assertIn("Summary is required", errors)
        self.assertIn("File Name is required", errors)
        rows = ctx.settings.get("sections.items")
        rows[0]["min_words"], rows[0]["max_words"] = 5, 8
        self.client.update_settings({"sections.items": rows})
        ctx = engine.load_context(self.client)
        self.assertIn("Summary must be 5-8 words",
                      engine.validation_errors(ctx.settings, {"summary": "too short"}, "X", "alice"))
        with self.assertRaises(engine.GenerationError):
            engine.generate(ctx, {"summary": "too short"}, "X")

    def test_typography_overrides_and_settings_from_cache(self) -> None:
        ctx = self._with_format()
        texts = {"summary": "One. Two.", "skills": "A: b", "top_skills": "k", "experience": "Co | X   2020 - 2021\n- y"}
        self.world.http.calls.clear()
        path = engine.generate(ctx, texts, "Sized", typography={"font_name": "Georgia", "body_size": 13})
        self.assertEqual(self.world.http.calls, [])  # generation itself needs no server call
        document = Document(str(path))
        fonts = {r.font.name for p in document.paragraphs for r in p.runs if r.text.strip()}
        self.assertEqual(fonts, {"Georgia"})


if __name__ == "__main__":
    unittest.main()
