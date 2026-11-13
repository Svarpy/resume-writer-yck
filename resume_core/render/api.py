"""Public resume generation API."""

from __future__ import annotations

from pathlib import Path


def build_resume(content, fmt, output_path: Path) -> Path:
    """Generate a resume DOCX from the format's template document (see ``resume_core.placeholders``)."""
    from resume_core.placeholders.api import build_resume as _build  # imported late: it uses render.parse

    return _build(content, fmt, output_path)
