"""MCP tools. They call the same client + engine as the desktop app; documents are written on this machine.

The AI app only ever receives short text results: ``success`` or ``failure: <reason>`` for actions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from mcp.server.mcpserver import MCPServer

from resume_client import ClientError, ResumeClient, engine, load_client_config
from resume_core.settings import SETTING_DEFS_BY_KEY

INSTRUCTIONS = """\
Resume Writer creates Word resumes on the user's own computer from their uploaded sample format.
1. Call list_sections to see which sections to write for the default format (keys, labels, requirements).
2. Write the text for each section and call generate_resume(company, sections).
It returns "success" or "failure: <reason>"; fix what the reason says and retry. Files are saved to the
user's output folder; no file content is sent back.
"""


def ok() -> str:
    return "success"


def fail(reason: str) -> str:
    return f"failure: {reason}"


class ResumeTools:
    """The tool implementations, kept as plain methods so they are easy to test."""

    def __init__(self, client_factory: Optional[Callable[[], ResumeClient]] = None) -> None:
        self._factory = client_factory or self._default_client
        self._client: Optional[ResumeClient] = None

    @staticmethod
    def _default_client() -> ResumeClient:
        client = ResumeClient(load_client_config())
        client.use_access_token()
        return client

    @property
    def client(self) -> ResumeClient:
        if self._client is None:
            self._client = self._factory()
        return self._client

    def _guard(self, action: Callable[[], str]) -> str:
        try:
            return action()
        except ClientError as exc:
            return fail(str(exc))
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to the AI app
            return fail(f"unexpected error: {exc}")

    # -- tools ---------------------------------------------------------------------------
    def get_status(self) -> str:
        """Signed-in user, default format and where resumes are saved."""
        def run() -> str:
            ctx = engine.load_context(self.client)
            return json.dumps({
                "user": self.client.username, "default_format": ctx.format_info["name"],
                "output_directory": str(engine.output_directory(ctx.settings)),
            })
        return self._guard(run)

    def list_sections(self) -> str:
        """Sections to provide to generate_resume for the default format."""
        def run() -> str:
            ctx = engine.load_context(self.client)
            required = set(ctx.settings.required_fields())
            return json.dumps({
                "company_required": "file_name" in required,
                "sections": [
                    {"key": s["key"], "label": s["label"], "kind": s["kind"], "required": s["key"] in required,
                     "min_words": s["min_words"], "max_words": s["max_words"]}
                    for s in ctx.settings.writer_sections()
                ],
            })
        return self._guard(run)

    def generate_resume(self, company: str, sections: dict[str, str]) -> str:
        """Generate a resume on this computer. ``sections`` maps a section key (see list_sections) to its text."""
        def run() -> str:
            ctx = engine.load_context(self.client)
            by_label = {s["label"].casefold(): s["key"] for s in ctx.settings.writer_sections()}
            texts = {by_label.get(str(k).casefold(), str(k)): str(v) for k, v in (sections or {}).items()}
            unknown = sorted(set(texts) - {s["key"] for s in ctx.settings.writer_sections()})
            if unknown:
                return fail(f"unknown section(s): {', '.join(unknown)}")
            engine.generate(ctx, texts, company or "")
            return ok()
        return self._guard(run)

    def check_duplicate(self, company: str) -> str:
        """Whether a resume for this company already exists (``none`` or the matching file names)."""
        def run() -> str:
            ctx = engine.load_context(self.client)
            names = [p.name for p in engine.duplicate_files(ctx.settings, company or "")]
            return ", ".join(names) if names else "none"
        return self._guard(run)

    def list_formats(self) -> str:
        """The user's resume formats and which one is the default."""
        return self._guard(lambda: json.dumps(
            [{"id": f["id"], "name": f["name"], "default": f["is_default"]} for f in self.client.list_formats()]))

    def set_default_format(self, format: str) -> str:
        """Make a format (id or name) the default."""
        def run() -> str:
            wanted = next((f for f in self.client.list_formats()
                           if format in (f["id"], f["name"]) or f["name"].casefold() == format.casefold()), None)
            if wanted is None:
                return fail(f"no format named '{format}'")
            self.client.set_default_format(wanted["id"])
            return ok()
        return self._guard(run)

    def upload_format(self, name: str, file_path: str) -> str:
        """Upload a sample .docx (a path on this computer) as a new format."""
        def run() -> str:
            path = Path(file_path).expanduser()
            if not path.is_file():
                return fail(f"file not found: {path}")
            self.client.add_format(name, path)
            return ok()
        return self._guard(run)

    def get_settings(self, keys: Optional[list[str]] = None) -> str:
        """Current settings (all, or only the given dotted keys such as ``output.directory``)."""
        def run() -> str:
            values = self.client.settings().values
            if keys:
                missing = [k for k in keys if k not in values]
                if missing:
                    return fail(f"unknown setting(s): {', '.join(missing)}")
                values = {k: values[k] for k in keys}
            return json.dumps(values, ensure_ascii=False)
        return self._guard(run)

    def update_settings(self, changes: dict[str, Any]) -> str:
        """Change settings, e.g. ``{"personal.phone": "+1 555 0100"}``. Invalid values are rejected."""
        def run() -> str:
            unknown = [k for k in changes if k not in SETTING_DEFS_BY_KEY]
            if unknown:
                return fail(f"unknown setting(s): {', '.join(unknown)}")
            self.client.update_settings(changes)
            return ok()
        return self._guard(run)


def build_server(tools: Optional[ResumeTools] = None) -> MCPServer:
    tools = tools or ResumeTools()
    server = MCPServer("resume-writer", instructions=INSTRUCTIONS)
    for method in (tools.get_status, tools.list_sections, tools.generate_resume, tools.check_duplicate,
                   tools.list_formats, tools.set_default_format, tools.upload_format, tools.get_settings,
                   tools.update_settings):
        server.add_tool(method)
    return server
