"""Format data models, defaults, and section-key helpers."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Optional

DEFAULT_FORMAT_ID = "default"
DEFAULT_FORMAT_NAME = "Default Application Format"
FORMAT_XML_VERSION = "3"

# Historical writer defaults (must stay in sync with ResumeFormat / page setup).
DEFAULT_FORMAT_VALUES: dict[str, Any] = {
    "font_name": "Arial",
    "name_size": 16,
    "heading_size": 12,
    "body_size": 11,
    "page_width_in": 8.5,
    "page_height_in": 11.0,
    "margin_top_in": 0.75,
    "margin_right_in": 0.75,
    "margin_bottom_in": 0.75,
    "margin_left_in": 0.75,
    "header_distance_in": 0.4917,
    "footer_distance_in": 0.4917,
    "line_spacing": 1.0,
}

# Canonical keys accepted by ``resume_writer_app.build_resume`` section renderers.
CANONICAL_SECTION_KEYS: tuple[str, ...] = (
    "summary",
    "skills",
    "experience",
    "education",
    "certifications",
)

# Map common heading phrases → canonical section keys used by the writer.
_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "professional summary", "profile", "objective"),
    "skills": ("skills", "technical skills", "core competencies", "core skills"),
    "experience": (
        "work experience",
        "experience",
        "employment",
        "professional experience",
        "work history",
        "career history",
        "employment history",
    ),
    "education": ("education", "academic background", "academics"),
    "certifications": ("certifications", "certificates", "licenses", "licences"),
}


class FormatError(Exception):
    """Base class for format-store errors."""


class FormatNotFoundError(FormatError):
    pass


class FormatProtectedError(FormatError):
    pass


class FormatValidationError(FormatError):
    pass


@dataclass
class SeparatorStyle:
    """Horizontal rule drawn between resume sections (paragraph bottom border)."""

    enabled: bool = True
    val: str = "single"
    sz: int = 2
    space: int = 1
    color: str = "AAAAAA"


@dataclass
class HeadingStyle:
    bold: bool = True
    space_before_pt: float = 8.0
    space_after_pt: float = 3.0
    alignment: str = "left"  # left | center | right | justify


@dataclass
class ExperienceLayout:
    """How company / role / duration lines are composed in WORK EXPERIENCE."""

    # two_column_table | tabbed_line | single_line
    company_line_mode: str = "two_column_table"
    left_width_in: float = 4.45
    right_width_in: float = 2.55
    tab_pos_twips: int = 9200
    company_bold: bool = True
    duration_bold: bool = True
    duration_align: str = "right"
    role_below_company: bool = True
    bullets_under_role: bool = True
    bullet_marker: str = "•"


@dataclass
class PageBorderStyle:
    """Optional page-edge borders from sectPr/pgBorders."""

    enabled: bool = False
    val: str = "single"
    sz: int = 4
    space: int = 24
    color: str = "000000"
    sides: tuple[str, ...] = ("top", "left", "bottom", "right")


@dataclass
class SectionRule:
    key: str
    heading: str
    separator_before: bool = True
    order: int = 0
    # Index of the heading block in the stored template body (excludes sectPr).
    template_block_index: int = -1
    # First body block after the heading belonging to this section (-1 if unknown).
    content_start_index: int = -1
    # Exclusive end index of the section's content region (-1 if unknown).
    content_end_index: int = -1


@dataclass
class DocumentStructure:
    """Structural rules extracted from a template (or the historical default)."""

    sections: list[SectionRule] = field(default_factory=list)
    separator: SeparatorStyle = field(default_factory=SeparatorStyle)
    heading_style: HeadingStyle = field(default_factory=HeadingStyle)
    experience: ExperienceLayout = field(default_factory=ExperienceLayout)
    page_border: PageBorderStyle = field(default_factory=PageBorderStyle)
    contact_separator: str = "  |  "
    name_alignment: str = "left"
    contact_alignment: str = "left"
    # Body-block index of the first empty separator paragraph in the template.
    separator_block_index: int = -1
    # Body-block index of the first two-column experience table (-1 if none).
    experience_table_index: int = -1

    def section_for(self, key: str) -> Optional[SectionRule]:
        """Return the rule for ``key``, accepting synthetic/alias keys via heading text."""
        target = canonicalize_section_key(key)
        for section in self.sections:
            if canonicalize_section_key(section.key, section.heading) == target:
                return section
        return None

    def ordered_content_keys(self) -> list[str]:
        """Return canonical content section keys in template order.

        Synthetic extract keys (e.g. ``professional_experience``) are mapped to
        renderer keys while preserving custom heading labels on the SectionRule.
        """
        content_keys = set(CANONICAL_SECTION_KEYS)
        ordered: list[str] = []
        seen: set[str] = set()
        for section in sorted(self.sections, key=lambda s: s.order):
            canonical = canonicalize_section_key(section.key, section.heading)
            if canonical not in content_keys or canonical in seen:
                continue
            ordered.append(canonical)
            seen.add(canonical)
        for key in CANONICAL_SECTION_KEYS:
            if key not in seen:
                ordered.append(key)
        return ordered


def default_document_structure() -> DocumentStructure:
    """Historical Resume Writer layout (Default Application Format)."""
    return DocumentStructure(
        sections=[
            SectionRule("summary", "SUMMARY", separator_before=True, order=0),
            SectionRule("skills", "SKILLS", separator_before=True, order=1),
            SectionRule("experience", "WORK EXPERIENCE", separator_before=True, order=2),
            SectionRule("education", "EDUCATION", separator_before=True, order=3),
            SectionRule("certifications", "Certifications", separator_before=True, order=4),
        ],
        separator=SeparatorStyle(),
        heading_style=HeadingStyle(),
        experience=ExperienceLayout(),
        page_border=PageBorderStyle(enabled=False),
        contact_separator="  |  ",
        name_alignment="left",
        contact_alignment="left",
    )


@dataclass
class ResumeFormatSpec:
    """Serializable resume layout/typography used by the writer and Formatter UI."""

    id: str
    name: str
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
    protected: bool = False
    source: str = "manual"  # manual | docx | default
    # Relative filename under the user's formats dir (e.g. "{id}.template.docx").
    # Absent for the protected default and manually created formats.
    template_file: Optional[str] = None

    def to_writer_kwargs(self) -> dict[str, Any]:
        """Subset accepted by ``resume_writer_app.ResumeFormat``."""
        return {
            "font_name": self.font_name,
            "name_size": int(self.name_size),
            "heading_size": int(self.heading_size),
            "body_size": int(self.body_size),
            "page_width_in": float(self.page_width_in),
            "page_height_in": float(self.page_height_in),
            "margin_top_in": float(self.margin_top_in),
            "margin_right_in": float(self.margin_right_in),
            "margin_bottom_in": float(self.margin_bottom_in),
            "margin_left_in": float(self.margin_left_in),
            "header_distance_in": float(self.header_distance_in),
            "footer_distance_in": float(self.footer_distance_in),
            "line_spacing": float(normalize_line_spacing(self.line_spacing)),
            "structure": self.structure,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "protected": self.protected,
            "source": self.source,
            "font_name": self.font_name,
            "name_size": self.name_size,
            "heading_size": self.heading_size,
            "body_size": self.body_size,
            "section_count": len(self.structure.sections),
            "has_separators": self.structure.separator.enabled,
            "has_template": bool(self.template_file),
        }

    def has_template(self) -> bool:
        return bool(self.template_file)


def default_format_spec() -> ResumeFormatSpec:
    return ResumeFormatSpec(
        id=DEFAULT_FORMAT_ID,
        name=DEFAULT_FORMAT_NAME,
        protected=True,
        source="default",
        structure=default_document_structure(),
        **{k: v for k, v in DEFAULT_FORMAT_VALUES.items()},
    )


def normalize_line_spacing(value: Any) -> float:
    """Return a python-docx multiplier (≈0.5–3.0).

    Word styles often use EXACT line spacing as a Length (EMUs/twips). Casting
    that Length with ``float()`` yields ~152400, which must not be used as a
    multiplier — python-docx would compute ``Emu(value * Twips(240))`` and overflow.
    """
    if value is None:
        return float(DEFAULT_FORMAT_VALUES["line_spacing"])

    try:
        from docx.shared import Length

        if isinstance(value, Length):
            emus = int(value)
            if emus <= 0:
                return float(DEFAULT_FORMAT_VALUES["line_spacing"])
            # Single-line exact spacing is 240 twips == 152400 EMUs.
            return max(0.5, min(3.0, emus / 152400.0))
    except Exception:
        pass

    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(DEFAULT_FORMAT_VALUES["line_spacing"])

    if 0.5 <= number <= 3.0:
        return number
    # Raw EMUs mistaken for a multiplier.
    if number > 1000:
        return max(0.5, min(3.0, number / 152400.0))
    # Raw twips mistaken for a multiplier.
    if number > 3.0:
        return max(0.5, min(3.0, number / 240.0))
    return float(DEFAULT_FORMAT_VALUES["line_spacing"])


def _normalize_heading_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _match_section_key(heading_text: str) -> Optional[str]:
    normalized = _normalize_heading_text(heading_text)
    if not normalized:
        return None
    for key, aliases in _SECTION_ALIASES.items():
        if normalized in aliases:
            return key
    # Prefix match for headings like "WORK EXPERIENCE (SELECTED)"
    for key, aliases in _SECTION_ALIASES.items():
        for alias in aliases:
            if normalized.startswith(alias):
                return key
    return None


def canonicalize_section_key(key: str, heading: str = "") -> str:
    """Map synthetic or alias section keys to writer renderer keys.

    Extraction may persist keys like ``professional_experience`` when a heading
    is not recognized up front. Generation must still bind those rules to the
    ``experience`` renderer while keeping the custom heading label.
    """
    raw = (key or "").strip()
    if raw in CANONICAL_SECTION_KEYS:
        return raw
    # Underscore/hyphen slugs → phrase form for alias matching.
    slug_as_phrase = re.sub(r"[_\-]+", " ", raw)
    matched = _match_section_key(slug_as_phrase) or _match_section_key(raw)
    if matched:
        return matched
    if heading:
        matched = _match_section_key(heading)
        if matched:
            return matched
    return raw

