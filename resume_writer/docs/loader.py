"""Load selected sections from documentation.md for in-app display."""

from __future__ import annotations

import re
from pathlib import Path


def documentation_path() -> Path:
    return Path(__file__).resolve().parent / "documentation.md"


def load_markdown_section(heading: str, *, path: Path | None = None) -> str:
    """Return the body under ``## {heading}`` until the next ``## `` heading.

    Heading match is case-sensitive against the markdown title text after ``## ``.
    """
    doc_path = path or documentation_path()
    if not doc_path.is_file():
        return f"Documentation file not found:\n{doc_path}"

    text = doc_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return f'Section "{heading}" was not found in documentation.md.'

    start = match.end()
    next_heading = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    body = text[start:end].strip()
    return body or f'Section "{heading}" is empty.'


def load_how_to_use_section(*, path: Path | None = None) -> str:
    return load_markdown_section("How To Use The Application", path=path)
