"""Render-time resume models and store→writer format adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from formats_store import (
    DEFAULT_FORMAT_VALUES,
    DocumentStructure,
    default_document_structure,
    get_format_for_writer,
    resolve_format_template_path,
)
from user_auth import get_current_user


@dataclass(frozen=True)
class ResumeFormat:
    font_name: str = DEFAULT_FORMAT_VALUES["font_name"]
    name_size: int = DEFAULT_FORMAT_VALUES["name_size"]
    heading_size: int = DEFAULT_FORMAT_VALUES["heading_size"]
    body_size: int = DEFAULT_FORMAT_VALUES["body_size"]
    page_width_in: float = DEFAULT_FORMAT_VALUES["page_width_in"]
    page_height_in: float = DEFAULT_FORMAT_VALUES["page_height_in"]
    margin_top_in: float = DEFAULT_FORMAT_VALUES["margin_top_in"]
    margin_right_in: float = DEFAULT_FORMAT_VALUES["margin_right_in"]
    margin_bottom_in: float = DEFAULT_FORMAT_VALUES["margin_bottom_in"]
    margin_left_in: float = DEFAULT_FORMAT_VALUES["margin_left_in"]
    header_distance_in: float = DEFAULT_FORMAT_VALUES["header_distance_in"]
    footer_distance_in: float = DEFAULT_FORMAT_VALUES["footer_distance_in"]
    line_spacing: float = DEFAULT_FORMAT_VALUES["line_spacing"]
    structure: DocumentStructure = field(default_factory=default_document_structure)
    template_path: Optional[Path] = None


def resume_format_from_store(username: Optional[str] = None) -> ResumeFormat:
    """Build a ResumeFormat from the user's primary format (or app default).

    When the primary format was uploaded from Word, ``template_path`` points at
    the stored package so generate can clone it.
    """
    try:
        user = username if username is not None else get_current_user()
        spec = get_format_for_writer(user)
        kwargs = spec.to_writer_kwargs()
        if user:
            template = resolve_format_template_path(user, spec)
            if template is not None:
                kwargs["template_path"] = template
        return ResumeFormat(**kwargs)
    except Exception:
        return ResumeFormat()


def _alignment_from_name(name: str):
    mapping = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }
    return mapping.get((name or "left").strip().lower(), WD_ALIGN_PARAGRAPH.LEFT)


@dataclass(frozen=True)
class ResumeContent:
    name: str
    email: str
    phone: str
    location: str
    summary: str
    skills: str
    experience: str
    certifications: str
    top_skills: str
    education_entries: Tuple[str, ...]
