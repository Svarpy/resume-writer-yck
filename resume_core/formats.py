"""Resume formats: what is learned from an uploaded sample document.

A *format* is one sample ``.docx``. Uploading it produces:

* ``FormatInfo`` - small JSON-friendly metadata (name, font, sizes, sections found);
* ``settings_defaults`` - starting values for the format-scoped settings (Resume Sections,
  Fonts, Required Fields) derived from the sample.

The sample file itself is stored separately by whoever persists formats (the server).
"""

from __future__ import annotations

import copy
import io
from dataclasses import asdict, dataclass, field
from typing import Any

from resume_core.ooxml.analysis import DocumentAnalysis, analyze_document
from resume_core.settings.schema import (
    FILE_NAME_FIELD,
    FORMAT_SCOPED_KEYS,
    SETTING_DEFS_BY_KEY,
)

KEYWORDS_SECTION_KEY = "top_skills"


class FormatError(ValueError):
    """The uploaded document cannot be used as a resume format."""


@dataclass
class FormatInfo:
    id: str
    name: str
    font_name: str = "Arial"
    name_size: int = 16
    heading_size: int = 12
    body_size: int = 11
    sections: list[dict[str, str]] = field(default_factory=list)  # [{key, heading, kind}]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "FormatInfo":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})

    def typography(self) -> dict[str, Any]:
        return {
            "font_name": self.font_name,
            "name_size": self.name_size,
            "heading_size": self.heading_size,
            "body_size": self.body_size,
        }


def _with(values: list[int], *extra: int) -> list[int]:
    merged = list(values)
    for number in extra:
        if number and number not in merged:
            merged.append(number)
    return sorted(merged)


def settings_defaults_from_analysis(analysis: DocumentAnalysis) -> dict[str, Any]:
    """Starting values of the format-scoped settings for a sample (its sections, fonts, required fields)."""
    defaults = {key: copy.deepcopy(SETTING_DEFS_BY_KEY[key].default) for key in FORMAT_SCOPED_KEYS}
    if not analysis.regions:
        return defaults
    sections = analysis.section_summary()
    sections.append({
        "key": KEYWORDS_SECTION_KEY, "label": "Top 5 Skills For Metadata", "heading": "", "kind": "keywords",
        "width": "half", "enabled": True, "show_heading": True, "min_words": 0, "max_words": 0,
    })
    defaults["sections.items"] = sections
    defaults["validation.required_fields"] = [
        row["key"] for row in sections if row["kind"] in ("paragraph", "skills", "experience", "keywords")
    ] + [FILE_NAME_FIELD]
    fonts = list(defaults["fonts.font_choices"])
    if analysis.font_name and analysis.font_name.casefold() not in {f.casefold() for f in fonts}:
        fonts.append(analysis.font_name)
    defaults["fonts.font_choices"] = fonts
    defaults["fonts.name_size_choices"] = _with(defaults["fonts.name_size_choices"], analysis.name_size)
    defaults["fonts.heading_size_choices"] = _with(defaults["fonts.heading_size_choices"], analysis.heading_size)
    defaults["fonts.body_size_choices"] = _with(defaults["fonts.body_size_choices"], analysis.body_size)
    return defaults


def analyze_sample(data: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read an uploaded ``.docx`` and return ``(info fields, settings defaults)``.

    The info fields lack ``id`` and ``name`` (chosen by the caller).
    """
    from docx import Document

    if not data[:2] == b"PK":
        raise FormatError("Only .docx Word documents can be used as a resume format.")
    try:
        analysis = analyze_document(Document(io.BytesIO(data)))
    except Exception as exc:  # noqa: BLE001 - corrupt or unsupported packages
        raise FormatError(f"Could not read the Word document: {exc}") from exc
    if not analysis.regions and analysis.name is None:
        raise FormatError("The document has no recognisable resume content (no name or section headings).")
    info = {
        "font_name": analysis.font_name or "Arial",
        "name_size": analysis.name_size,
        "heading_size": analysis.heading_size,
        "body_size": analysis.body_size,
        "sections": [
            {"key": row["key"], "heading": row["heading"] or row["label"], "kind": row["kind"]}
            for row in analysis.section_summary()
        ],
        "warnings": list(analysis.warnings),
    }
    return info, settings_defaults_from_analysis(analysis)
