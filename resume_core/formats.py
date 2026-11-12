"""Resume formats: what is learned from an uploaded template document.

A *format* is one template ``.docx`` (a resume with ``{{placeholders}}``, see ``resume_core.placeholders``).
Uploading it produces:

* ``FormatInfo`` - small JSON-friendly metadata (name, font, sizes, sections found, outline);
* ``settings_defaults`` - starting values for the format-scoped settings (Resume Sections,
  Fonts, Required Fields) derived from the template.

The template file itself is stored separately by whoever persists formats (the server).
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any

from resume_core.placeholders import TemplateError, TemplateInfo, inspect_template
from resume_core.settings.schema import (
    FILE_NAME_FIELD,
    FORMAT_SCOPED_KEYS,
    SETTING_DEFS_BY_KEY,
)

KEYWORDS_SECTION_KEY = "top_skills"


class FormatError(ValueError):
    """The uploaded document cannot be used as a resume format."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = list(errors or [message])


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
    outline: list[str] = field(default_factory=list)              # e.g. "experience > jobs(company) > roles(title)"

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


def settings_defaults_from_template(info: TemplateInfo) -> dict[str, Any]:
    """Starting values of the format-scoped settings for a template (its sections, fonts, required fields)."""
    defaults = {key: copy.deepcopy(SETTING_DEFS_BY_KEY[key].default) for key in FORMAT_SCOPED_KEYS}
    sections = [dict(row) for row in info.sections]
    sections.append({
        "key": KEYWORDS_SECTION_KEY, "label": "Top 5 Skills For Metadata", "heading": "", "kind": "keywords",
        "width": "half", "enabled": True, "show_heading": True, "min_words": 0, "max_words": 0,
    })
    defaults["sections.items"] = sections
    defaults["validation.required_fields"] = [
        row["key"] for row in sections if row["kind"] in ("paragraph", "skills", "experience", "keywords")
    ] + [FILE_NAME_FIELD]
    fonts = list(defaults["fonts.font_choices"])
    if info.font_name and info.font_name.casefold() not in {f.casefold() for f in fonts}:
        fonts.append(info.font_name)
    defaults["fonts.font_choices"] = fonts
    defaults["fonts.name_size_choices"] = _with(defaults["fonts.name_size_choices"], info.name_size)
    defaults["fonts.heading_size_choices"] = _with(defaults["fonts.heading_size_choices"], info.heading_size)
    defaults["fonts.body_size_choices"] = _with(defaults["fonts.body_size_choices"], info.body_size)
    return defaults


def analyze_template(data: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read an uploaded template ``.docx`` and return ``(info fields, settings defaults)``.

    The info fields lack ``id`` and ``name`` (chosen by the caller). Raises ``FormatError`` with every
    problem found when the document is not a usable template.
    """
    try:
        template = inspect_template(data)
    except TemplateError as exc:
        raise FormatError(str(exc)) from exc
    if not template.ok:
        raise FormatError("The template has problems: " + "; ".join(template.errors), template.errors)
    info = {
        "font_name": template.font_name or "Arial",
        "name_size": template.name_size or 16,
        "heading_size": template.heading_size or 12,
        "body_size": template.body_size or 11,
        "sections": [
            {"key": row["key"], "heading": row["heading"] or row["label"], "kind": row["kind"]}
            for row in template.sections
        ],
        "warnings": list(template.warnings),
        "outline": list(template.outline),
    }
    return info, settings_defaults_from_template(template)
