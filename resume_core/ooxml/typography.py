"""Font and sizes of a sample document, read from the document itself (cached per file version)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=32)
def _typography(path: str, mtime_ns: int) -> Optional[dict]:
    from docx import Document

    from resume_core.ooxml.analysis import analyze_document

    analysis = analyze_document(Document(path))
    return {
        "font_name": analysis.font_name,
        "name_size": analysis.name_size,
        "heading_size": analysis.heading_size,
        "body_size": analysis.body_size,
    }


def template_typography(path: Path) -> Optional[dict]:
    """``{font_name, name_size, heading_size, body_size}`` of the sample, or None when unreadable."""
    try:
        return _typography(str(path), path.stat().st_mtime_ns)
    except Exception:  # noqa: BLE001
        return None
