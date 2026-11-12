"""MCP tools: results are short success/failure words and documents land on the local disk."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from resume_mcp.server import ResumeTools, build_server
from tests.support import FIXTURES, World


class McpToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = World()
        self.owner = self.world.login(signup=True)
        self.out = Path(tempfile.mkdtemp(prefix="rw-mcp-out-"))
        token = self.owner.create_token("claude")["token"]

        def factory():
            client = self.world.client()
            client.use_access_token(token)
            return client

        self.tools = ResumeTools(factory)

    def test_tools_are_registered(self) -> None:
        names = {tool.name for tool in asyncio.run(build_server(self.tools).list_tools())}
        self.assertEqual(names, {"get_status", "list_sections", "generate_resume", "check_duplicate", "list_formats",
                                 "set_default_format", "upload_format", "get_settings", "update_settings"})

    def test_everything_fails_politely_until_a_format_exists(self) -> None:
        for call in (self.tools.get_status, self.tools.list_sections, lambda: self.tools.generate_resume("X", {})):
            self.assertTrue(call().startswith("failure: No resume format"), call())

    def test_upload_set_default_generate_and_duplicate_flow(self) -> None:
        self.assertEqual(self.tools.upload_format("Ref", str(FIXTURES / "ycksample.docx")), "success")
        self.assertEqual(self.tools.upload_format("Other", str(FIXTURES / "rama.docx")), "success")
        self.assertTrue(self.tools.upload_format("Bad", "/no/such/file.docx").startswith("failure: file not found"))
        listed = json.loads(self.tools.list_formats())
        self.assertEqual([(f["name"], f["default"]) for f in listed], [("Ref", True), ("Other", False)])
        self.assertEqual(self.tools.set_default_format("other"), "success")  # by name, any case
        self.assertTrue(self.tools.set_default_format("nope").startswith("failure"))
        self.assertEqual(self.tools.set_default_format("Ref"), "success")

        self.assertEqual(self.tools.update_settings({"output.directory": str(self.out)}), "success")
        self.assertTrue(self.tools.update_settings({"output.filename_template": "bad"}).startswith("failure:"))
        self.assertTrue(self.tools.update_settings({"made.up": 1}).startswith("failure: unknown setting"))

        sections = json.loads(self.tools.list_sections())
        keys = [s["key"] for s in sections["sections"]]
        self.assertEqual(keys, ["summary", "skills", "experience", "top_skills"])
        self.assertTrue(sections["company_required"])

        body = {"summary": "A summary.", "Skills": "Languages: Python", "top_skills": "a, b",
                "experience": "Acme | Remote   May 2020 - Present\n- Built it"}
        self.assertEqual(self.tools.generate_resume("Acme", body), "success")  # labels work as well as keys
        files = list(self.out.glob("ResumeAcme*.docx"))
        self.assertEqual(len(files), 1)  # created on this machine, only a word went back
        self.assertEqual(self.tools.check_duplicate("acme"), files[0].name)
        self.assertEqual(self.tools.check_duplicate("Zzz"), "none")
        again = self.tools.generate_resume("Acme", body)
        self.assertTrue(again.startswith("failure:") and "already exists" in again)
        missing = self.tools.generate_resume("New", {"summary": "x"})
        self.assertTrue(missing.startswith("failure:") and "Skills is required" in missing)
        self.assertTrue(self.tools.generate_resume("New", {"bogus": "x"}).startswith("failure: unknown section"))

        settings = json.loads(self.tools.get_settings(["output.directory", "personal.name"]))
        self.assertEqual(settings["output.directory"], str(self.out))
        self.assertTrue(self.tools.get_settings(["nope"]).startswith("failure"))
        status = json.loads(self.tools.get_status())
        self.assertEqual((status["user"], status["default_format"]), ("alice", "Ref"))

    def test_server_down_is_reported_as_failure(self) -> None:
        self.tools.upload_format("Ref", str(FIXTURES / "ycksample.docx"))
        self.world.http.down = True
        try:
            tools = ResumeTools(lambda: self.world.client())
            self.assertTrue(tools.list_formats().startswith("failure"))
        finally:
            self.world.http.down = False


if __name__ == "__main__":
    unittest.main()
