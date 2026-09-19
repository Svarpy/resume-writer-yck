"""Per-user resume format store (XML) plus the protected application default.

The built-in ``default`` format mirrors the historical hardcoded layout in
``resume_writer_app.ResumeFormat`` / ``apply_document_defaults``. It is always
listed, cannot be edited or deleted, and is the fallback when no primary is set.

Format XML version 2 adds a ``<structure>`` block that captures section order,
heading labels, separators, experience line layout, and related page chrome.

Format XML version 3 adds template preservation for uploaded ``.docx`` files:
the original Word package is stored beside the format XML, and section anchors
map content regions so generate can clone the template rather than approximate it.
"""

from __future__ import annotations

import re
import shutil
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional
from xml.dom import minidom

from app_paths import sanitize_username, user_formats_dir
from user_auth import get_profile, update_profile

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

    company_line_mode: str = "two_column_table"  # two_column_table | single_line
    left_width_in: float = 4.45
    right_width_in: float = 2.55
    company_bold: bool = True
    duration_bold: bool = True
    duration_align: str = "right"
    role_below_company: bool = True
    bullets_under_role: bool = True


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
            "line_spacing": float(self.line_spacing),
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


def _slugify_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "format"


def _new_format_id(name: str) -> str:
    return f"{_slugify_name(name)}-{uuid.uuid4().hex[:8]}"


def _safe_format_id(format_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", format_id.strip())
    if not safe_id or safe_id == DEFAULT_FORMAT_ID:
        raise FormatValidationError("Invalid format id")
    return safe_id


def _format_path(username: str, format_id: str) -> Path:
    if format_id == DEFAULT_FORMAT_ID:
        raise FormatProtectedError("Default format is not stored as a user file")
    return user_formats_dir(username) / f"{_safe_format_id(format_id)}.xml"


def _template_filename(format_id: str) -> str:
    return f"{_safe_format_id(format_id)}.template.docx"


def format_template_path(username: str, format_id: str) -> Path:
    """Absolute path where an uploaded template ``.docx`` would be stored."""
    return user_formats_dir(username) / _template_filename(format_id)


def resolve_format_template_path(username: str, spec: ResumeFormatSpec) -> Optional[Path]:
    """Return the on-disk template for a format, or ``None`` if absent/default."""
    if spec.id == DEFAULT_FORMAT_ID or not spec.template_file:
        return None
    path = user_formats_dir(username) / Path(spec.template_file).name
    return path if path.is_file() else None


def _text(parent: ET.Element, tag: str, default: str = "") -> str:
    node = parent.find(tag)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _require_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise FormatValidationError(f"Invalid numeric value for {field_name}") from exc


def _require_int(value: str, field_name: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError) as exc:
        raise FormatValidationError(f"Invalid integer value for {field_name}") from exc


def _bool_text(value: str, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _structure_to_xml(parent: ET.Element, structure: DocumentStructure) -> None:
    root = ET.SubElement(parent, "structure")

    sections_el = ET.SubElement(root, "sections")
    for section in structure.sections:
        sec = ET.SubElement(sections_el, "section", {"key": section.key, "order": str(section.order)})
        ET.SubElement(sec, "heading").text = section.heading
        ET.SubElement(sec, "separatorBefore").text = "true" if section.separator_before else "false"
        ET.SubElement(sec, "templateBlockIndex").text = str(int(section.template_block_index))
        ET.SubElement(sec, "contentStartIndex").text = str(int(section.content_start_index))
        ET.SubElement(sec, "contentEndIndex").text = str(int(section.content_end_index))

    sep = ET.SubElement(root, "separator")
    ET.SubElement(sep, "enabled").text = "true" if structure.separator.enabled else "false"
    ET.SubElement(sep, "val").text = structure.separator.val
    ET.SubElement(sep, "sz").text = str(int(structure.separator.sz))
    ET.SubElement(sep, "space").text = str(int(structure.separator.space))
    ET.SubElement(sep, "color").text = structure.separator.color

    heading = ET.SubElement(root, "headingStyle")
    ET.SubElement(heading, "bold").text = "true" if structure.heading_style.bold else "false"
    ET.SubElement(heading, "spaceBeforePt").text = str(structure.heading_style.space_before_pt)
    ET.SubElement(heading, "spaceAfterPt").text = str(structure.heading_style.space_after_pt)
    ET.SubElement(heading, "alignment").text = structure.heading_style.alignment

    exp = ET.SubElement(root, "experienceLayout")
    ET.SubElement(exp, "companyLineMode").text = structure.experience.company_line_mode
    ET.SubElement(exp, "leftWidthIn").text = str(structure.experience.left_width_in)
    ET.SubElement(exp, "rightWidthIn").text = str(structure.experience.right_width_in)
    ET.SubElement(exp, "companyBold").text = "true" if structure.experience.company_bold else "false"
    ET.SubElement(exp, "durationBold").text = "true" if structure.experience.duration_bold else "false"
    ET.SubElement(exp, "durationAlign").text = structure.experience.duration_align
    ET.SubElement(exp, "roleBelowCompany").text = "true" if structure.experience.role_below_company else "false"
    ET.SubElement(exp, "bulletsUnderRole").text = "true" if structure.experience.bullets_under_role else "false"

    border = ET.SubElement(root, "pageBorder")
    ET.SubElement(border, "enabled").text = "true" if structure.page_border.enabled else "false"
    ET.SubElement(border, "val").text = structure.page_border.val
    ET.SubElement(border, "sz").text = str(int(structure.page_border.sz))
    ET.SubElement(border, "space").text = str(int(structure.page_border.space))
    ET.SubElement(border, "color").text = structure.page_border.color
    ET.SubElement(border, "sides").text = ",".join(structure.page_border.sides)

    ET.SubElement(root, "contactSeparator").text = structure.contact_separator
    ET.SubElement(root, "nameAlignment").text = structure.name_alignment
    ET.SubElement(root, "contactAlignment").text = structure.contact_alignment
    ET.SubElement(root, "separatorBlockIndex").text = str(int(structure.separator_block_index))
    ET.SubElement(root, "experienceTableIndex").text = str(int(structure.experience_table_index))


def _structure_from_xml(root: ET.Element) -> DocumentStructure:
    structure_el = root.find("structure")
    if structure_el is None:
        return default_document_structure()

    base = default_document_structure()
    sections: list[SectionRule] = []
    sections_el = structure_el.find("sections")
    if sections_el is not None:
        for sec in sections_el.findall("section"):
            key = (sec.attrib.get("key") or "").strip()
            if not key:
                continue
            order = _require_int(sec.attrib.get("order", str(len(sections))), "section.order")
            heading = _text(sec, "heading", key.upper())
            separator_before = _bool_text(_text(sec, "separatorBefore", "true"), True)
            key = canonicalize_section_key(key, heading)
            sections.append(
                SectionRule(
                    key=key,
                    heading=heading,
                    separator_before=separator_before,
                    order=order,
                    template_block_index=_require_int(_text(sec, "templateBlockIndex", "-1"), "templateBlockIndex"),
                    content_start_index=_require_int(_text(sec, "contentStartIndex", "-1"), "contentStartIndex"),
                    content_end_index=_require_int(_text(sec, "contentEndIndex", "-1"), "contentEndIndex"),
                )
            )
    if not sections:
        sections = list(base.sections)

    sep_el = structure_el.find("separator")
    separator = SeparatorStyle(
        enabled=_bool_text(_text(sep_el, "enabled", "true"), True) if sep_el is not None else base.separator.enabled,
        val=_text(sep_el, "val", base.separator.val) if sep_el is not None else base.separator.val,
        sz=_require_int(_text(sep_el, "sz", str(base.separator.sz)), "separator.sz") if sep_el is not None else base.separator.sz,
        space=_require_int(_text(sep_el, "space", str(base.separator.space)), "separator.space")
        if sep_el is not None
        else base.separator.space,
        color=_text(sep_el, "color", base.separator.color) if sep_el is not None else base.separator.color,
    )

    head_el = structure_el.find("headingStyle")
    heading_style = HeadingStyle(
        bold=_bool_text(_text(head_el, "bold", "true"), True) if head_el is not None else base.heading_style.bold,
        space_before_pt=_require_float(_text(head_el, "spaceBeforePt", str(base.heading_style.space_before_pt)), "spaceBeforePt")
        if head_el is not None
        else base.heading_style.space_before_pt,
        space_after_pt=_require_float(_text(head_el, "spaceAfterPt", str(base.heading_style.space_after_pt)), "spaceAfterPt")
        if head_el is not None
        else base.heading_style.space_after_pt,
        alignment=_text(head_el, "alignment", base.heading_style.alignment) if head_el is not None else base.heading_style.alignment,
    )

    exp_el = structure_el.find("experienceLayout")
    experience = ExperienceLayout(
        company_line_mode=_text(exp_el, "companyLineMode", base.experience.company_line_mode)
        if exp_el is not None
        else base.experience.company_line_mode,
        left_width_in=_require_float(_text(exp_el, "leftWidthIn", str(base.experience.left_width_in)), "leftWidthIn")
        if exp_el is not None
        else base.experience.left_width_in,
        right_width_in=_require_float(_text(exp_el, "rightWidthIn", str(base.experience.right_width_in)), "rightWidthIn")
        if exp_el is not None
        else base.experience.right_width_in,
        company_bold=_bool_text(_text(exp_el, "companyBold", "true"), True) if exp_el is not None else base.experience.company_bold,
        duration_bold=_bool_text(_text(exp_el, "durationBold", "true"), True) if exp_el is not None else base.experience.duration_bold,
        duration_align=_text(exp_el, "durationAlign", base.experience.duration_align)
        if exp_el is not None
        else base.experience.duration_align,
        role_below_company=_bool_text(_text(exp_el, "roleBelowCompany", "true"), True)
        if exp_el is not None
        else base.experience.role_below_company,
        bullets_under_role=_bool_text(_text(exp_el, "bulletsUnderRole", "true"), True)
        if exp_el is not None
        else base.experience.bullets_under_role,
    )

    border_el = structure_el.find("pageBorder")
    sides_raw = _text(border_el, "sides", ",".join(base.page_border.sides)) if border_el is not None else ",".join(base.page_border.sides)
    sides = tuple(s.strip() for s in sides_raw.split(",") if s.strip()) or base.page_border.sides
    page_border = PageBorderStyle(
        enabled=_bool_text(_text(border_el, "enabled", "false"), False) if border_el is not None else False,
        val=_text(border_el, "val", base.page_border.val) if border_el is not None else base.page_border.val,
        sz=_require_int(_text(border_el, "sz", str(base.page_border.sz)), "pageBorder.sz")
        if border_el is not None
        else base.page_border.sz,
        space=_require_int(_text(border_el, "space", str(base.page_border.space)), "pageBorder.space")
        if border_el is not None
        else base.page_border.space,
        color=_text(border_el, "color", base.page_border.color) if border_el is not None else base.page_border.color,
        sides=sides,
    )

    return DocumentStructure(
        sections=sections,
        separator=separator,
        heading_style=heading_style,
        experience=experience,
        page_border=page_border,
        contact_separator=_text(structure_el, "contactSeparator", base.contact_separator) or base.contact_separator,
        name_alignment=_text(structure_el, "nameAlignment", base.name_alignment) or base.name_alignment,
        contact_alignment=_text(structure_el, "contactAlignment", base.contact_alignment) or base.contact_alignment,
        separator_block_index=_require_int(
            _text(structure_el, "separatorBlockIndex", str(base.separator_block_index)),
            "separatorBlockIndex",
        ),
        experience_table_index=_require_int(
            _text(structure_el, "experienceTableIndex", str(base.experience_table_index)),
            "experienceTableIndex",
        ),
    )


def format_spec_to_xml(spec: ResumeFormatSpec) -> str:
    root = ET.Element("resumeFormat", {"version": FORMAT_XML_VERSION, "id": spec.id})
    ET.SubElement(root, "name").text = spec.name
    ET.SubElement(root, "protected").text = "true" if spec.protected else "false"
    ET.SubElement(root, "source").text = spec.source

    typography = ET.SubElement(root, "typography")
    ET.SubElement(typography, "fontName").text = spec.font_name
    ET.SubElement(typography, "nameSize").text = str(int(spec.name_size))
    ET.SubElement(typography, "headingSize").text = str(int(spec.heading_size))
    ET.SubElement(typography, "bodySize").text = str(int(spec.body_size))

    page = ET.SubElement(root, "page")
    ET.SubElement(page, "widthInches").text = str(spec.page_width_in)
    ET.SubElement(page, "heightInches").text = str(spec.page_height_in)
    ET.SubElement(page, "marginTopInches").text = str(spec.margin_top_in)
    ET.SubElement(page, "marginRightInches").text = str(spec.margin_right_in)
    ET.SubElement(page, "marginBottomInches").text = str(spec.margin_bottom_in)
    ET.SubElement(page, "marginLeftInches").text = str(spec.margin_left_in)
    ET.SubElement(page, "headerDistanceInches").text = str(spec.header_distance_in)
    ET.SubElement(page, "footerDistanceInches").text = str(spec.footer_distance_in)

    spacing = ET.SubElement(root, "spacing")
    ET.SubElement(spacing, "lineSpacing").text = str(spec.line_spacing)

    _structure_to_xml(root, spec.structure or default_document_structure())

    if spec.template_file:
        ET.SubElement(root, "templateFile").text = spec.template_file

    rough = ET.tostring(root, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")
    return pretty.decode("utf-8")


def format_spec_from_xml(xml_text: str, *, fallback_id: str = "", fallback_name: str = "") -> ResumeFormatSpec:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise FormatValidationError(f"Invalid format XML: {exc}") from exc
    if root.tag != "resumeFormat":
        raise FormatValidationError("Root element must be <resumeFormat>")

    fmt_id = (root.attrib.get("id") or fallback_id or _new_format_id(fallback_name or "format")).strip()
    name = _text(root, "name", fallback_name or fmt_id)
    protected = _text(root, "protected", "false").lower() in {"1", "true", "yes"}
    source = _text(root, "source", "manual") or "manual"

    typography = root.find("typography")
    page = root.find("page")
    spacing = root.find("spacing")

    def typo(tag: str, default: Any) -> str:
        if typography is None:
            return str(default)
        return _text(typography, tag, str(default))

    def page_val(tag: str, default: Any) -> str:
        if page is None:
            return str(default)
        return _text(page, tag, str(default))

    line_spacing = DEFAULT_FORMAT_VALUES["line_spacing"]
    if spacing is not None:
        line_spacing = _require_float(_text(spacing, "lineSpacing", str(line_spacing)), "lineSpacing")

    template_file = _text(root, "templateFile", "") or None

    return ResumeFormatSpec(
        id=fmt_id,
        name=name,
        protected=protected,
        source=source,
        font_name=typo("fontName", DEFAULT_FORMAT_VALUES["font_name"]),
        name_size=_require_int(typo("nameSize", DEFAULT_FORMAT_VALUES["name_size"]), "nameSize"),
        heading_size=_require_int(typo("headingSize", DEFAULT_FORMAT_VALUES["heading_size"]), "headingSize"),
        body_size=_require_int(typo("bodySize", DEFAULT_FORMAT_VALUES["body_size"]), "bodySize"),
        page_width_in=_require_float(page_val("widthInches", DEFAULT_FORMAT_VALUES["page_width_in"]), "widthInches"),
        page_height_in=_require_float(page_val("heightInches", DEFAULT_FORMAT_VALUES["page_height_in"]), "heightInches"),
        margin_top_in=_require_float(page_val("marginTopInches", DEFAULT_FORMAT_VALUES["margin_top_in"]), "marginTopInches"),
        margin_right_in=_require_float(page_val("marginRightInches", DEFAULT_FORMAT_VALUES["margin_right_in"]), "marginRightInches"),
        margin_bottom_in=_require_float(page_val("marginBottomInches", DEFAULT_FORMAT_VALUES["margin_bottom_in"]), "marginBottomInches"),
        margin_left_in=_require_float(page_val("marginLeftInches", DEFAULT_FORMAT_VALUES["margin_left_in"]), "marginLeftInches"),
        header_distance_in=_require_float(
            page_val("headerDistanceInches", DEFAULT_FORMAT_VALUES["header_distance_in"]),
            "headerDistanceInches",
        ),
        footer_distance_in=_require_float(
            page_val("footerDistanceInches", DEFAULT_FORMAT_VALUES["footer_distance_in"]),
            "footerDistanceInches",
        ),
        line_spacing=line_spacing,
        structure=_structure_from_xml(root),
        template_file=template_file,
    )


def default_format_xml() -> str:
    return format_spec_to_xml(default_format_spec())


def _coerce_structure(value: Any) -> DocumentStructure:
    if value is None:
        return default_document_structure()
    if isinstance(value, DocumentStructure):
        return value
    if isinstance(value, dict):
        base = default_document_structure()
        sections_raw = value.get("sections") or []
        sections: list[SectionRule] = []
        for item in sections_raw:
            if isinstance(item, SectionRule):
                sections.append(item)
            elif isinstance(item, dict):
                sections.append(
                    SectionRule(
                        key=str(item.get("key", "")),
                        heading=str(item.get("heading", "")),
                        separator_before=bool(item.get("separator_before", True)),
                        order=int(item.get("order", len(sections))),
                    )
                )
        sections = [
            SectionRule(
                key=canonicalize_section_key(s.key, s.heading),
                heading=s.heading,
                separator_before=s.separator_before,
                order=s.order,
                template_block_index=getattr(s, "template_block_index", -1),
                content_start_index=getattr(s, "content_start_index", -1),
                content_end_index=getattr(s, "content_end_index", -1),
            )
            for s in sections
            if (s.key or "").strip()
        ]
        sep = value.get("separator", {})
        if isinstance(sep, SeparatorStyle):
            separator = sep
        elif isinstance(sep, dict):
            separator = SeparatorStyle(**{**asdict(base.separator), **sep})
        else:
            separator = base.separator
        head = value.get("heading_style", {})
        if isinstance(head, HeadingStyle):
            heading_style = head
        elif isinstance(head, dict):
            heading_style = HeadingStyle(**{**asdict(base.heading_style), **head})
        else:
            heading_style = base.heading_style
        exp = value.get("experience", {})
        if isinstance(exp, ExperienceLayout):
            experience = exp
        elif isinstance(exp, dict):
            experience = ExperienceLayout(**{**asdict(base.experience), **exp})
        else:
            experience = base.experience
        border = value.get("page_border", {})
        if isinstance(border, PageBorderStyle):
            page_border = border
        elif isinstance(border, dict):
            payload = {**asdict(base.page_border), **border}
            if isinstance(payload.get("sides"), list):
                payload["sides"] = tuple(payload["sides"])
            page_border = PageBorderStyle(**payload)
        else:
            page_border = base.page_border
        return DocumentStructure(
            sections=sections or list(base.sections),
            separator=separator,
            heading_style=heading_style,
            experience=experience,
            page_border=page_border,
            contact_separator=str(value.get("contact_separator", base.contact_separator)),
            name_alignment=str(value.get("name_alignment", base.name_alignment)),
            contact_alignment=str(value.get("contact_alignment", base.contact_alignment)),
        )
    return default_document_structure()


def _read_user_format(username: str, format_id: str) -> ResumeFormatSpec:
    path = _format_path(username, format_id)
    if not path.is_file():
        raise FormatNotFoundError(f"Format '{format_id}' not found")
    spec = format_spec_from_xml(path.read_text(encoding="utf-8"), fallback_id=format_id)
    # Never allow a user file to impersonate the protected default id.
    if spec.id == DEFAULT_FORMAT_ID:
        spec.id = format_id
    spec.protected = False
    return spec


def get_format(username: str, format_id: str) -> ResumeFormatSpec:
    key = sanitize_username(username)
    if format_id == DEFAULT_FORMAT_ID:
        return default_format_spec()
    return _read_user_format(key, format_id)


def list_formats(username: str) -> list[ResumeFormatSpec]:
    """Return the protected default plus the user's saved formats."""
    key = sanitize_username(username)
    formats = [default_format_spec()]
    formats_dir = user_formats_dir(key)
    for path in sorted(formats_dir.glob("*.xml")):
        try:
            formats.append(format_spec_from_xml(path.read_text(encoding="utf-8"), fallback_id=path.stem))
        except FormatValidationError:
            continue
    # De-dupe by id (default wins).
    seen: set[str] = set()
    unique: list[ResumeFormatSpec] = []
    for spec in formats:
        if spec.id in seen:
            continue
        seen.add(spec.id)
        if spec.id == DEFAULT_FORMAT_ID:
            spec = default_format_spec()
        unique.append(spec)
    return unique


def create_format(
    username: str,
    name: str,
    *,
    xml_text: Optional[str] = None,
    values: Optional[dict[str, Any]] = None,
    source: str = "manual",
    set_as_primary: bool = False,
) -> ResumeFormatSpec:
    """Create and persist a named format for the user."""
    key = sanitize_username(username)
    clean_name = name.strip()
    if not clean_name:
        raise FormatValidationError("Format name is required")

    fmt_id = _new_format_id(clean_name)
    if xml_text:
        spec = format_spec_from_xml(xml_text, fallback_id=fmt_id, fallback_name=clean_name)
        spec.id = fmt_id
        spec.name = clean_name
    else:
        base = default_format_spec()
        payload = asdict(base)
        payload.update(values or {})
        payload["id"] = fmt_id
        payload["name"] = clean_name
        payload["protected"] = False
        payload["source"] = source
        if "structure" in payload:
            payload["structure"] = _coerce_structure(payload["structure"])
        allowed = {f.name for f in fields(ResumeFormatSpec)}
        payload = {k: v for k, v in payload.items() if k in allowed}
        spec = ResumeFormatSpec(**payload)

    spec.protected = False
    spec.source = source
    if not isinstance(spec.structure, DocumentStructure):
        spec.structure = _coerce_structure(spec.structure)
    path = _format_path(key, spec.id)
    path.write_text(format_spec_to_xml(spec), encoding="utf-8")

    if set_as_primary:
        set_primary_format(key, spec.id)
    return spec


def update_format(
    username: str,
    format_id: str,
    *,
    name: Optional[str] = None,
    xml_text: Optional[str] = None,
    values: Optional[dict[str, Any]] = None,
) -> ResumeFormatSpec:
    key = sanitize_username(username)
    if format_id == DEFAULT_FORMAT_ID:
        raise FormatProtectedError("The default application format cannot be edited")

    existing = _read_user_format(key, format_id)
    if xml_text is not None:
        updated = format_spec_from_xml(xml_text, fallback_id=format_id, fallback_name=existing.name)
        updated.id = format_id
        if name is not None:
            updated.name = name.strip() or existing.name
        else:
            updated.name = existing.name
    else:
        payload = asdict(existing)
        if values:
            payload.update(values)
        if name is not None:
            payload["name"] = name.strip() or existing.name
        payload["id"] = format_id
        payload["protected"] = False
        if "structure" in payload:
            payload["structure"] = _coerce_structure(payload["structure"])
        allowed = {f.name for f in fields(ResumeFormatSpec)}
        payload = {k: v for k, v in payload.items() if k in allowed}
        updated = ResumeFormatSpec(**payload)

    updated.protected = False
    if not isinstance(updated.structure, DocumentStructure):
        updated.structure = _coerce_structure(updated.structure)
    path = _format_path(key, format_id)
    path.write_text(format_spec_to_xml(updated), encoding="utf-8")
    return updated


def delete_format(username: str, format_id: str) -> None:
    key = sanitize_username(username)
    if format_id == DEFAULT_FORMAT_ID:
        raise FormatProtectedError("The default application format cannot be deleted")
    path = _format_path(key, format_id)
    if not path.is_file():
        raise FormatNotFoundError(f"Format '{format_id}' not found")
    path.unlink()

    # If this was the primary, fall back to default.
    profile = get_profile(key)
    if profile.primary_format_id == format_id:
        update_profile(key, primary_format_id=DEFAULT_FORMAT_ID)


def set_primary_format(username: str, format_id: str) -> ResumeFormatSpec:
    """Persist the user's primary format id (must exist or be default)."""
    key = sanitize_username(username)
    spec = get_format(key, format_id)
    update_profile(key, primary_format_id=spec.id)
    return spec


def get_primary_format(username: str) -> ResumeFormatSpec:
    key = sanitize_username(username)
    profile = get_profile(key)
    fmt_id = profile.primary_format_id or DEFAULT_FORMAT_ID
    try:
        return get_format(key, fmt_id)
    except FormatNotFoundError:
        update_profile(key, primary_format_id=DEFAULT_FORMAT_ID)
        return default_format_spec()


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


def _paragraph_has_bottom_border(paragraph) -> bool:
    try:
        from docx.oxml.ns import qn
    except ImportError:
        return False
    p_pr = paragraph._p.pPr
    if p_pr is None:
        return False
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        return False
    bottom = p_bdr.find(qn("w:bottom"))
    if bottom is None:
        return False
    val = bottom.get(qn("w:val")) or ""
    return val not in {"", "nil", "none"}


def _read_bottom_border(paragraph) -> Optional[SeparatorStyle]:
    try:
        from docx.oxml.ns import qn
    except ImportError:
        return None
    p_pr = paragraph._p.pPr
    if p_pr is None:
        return None
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        return None
    bottom = p_bdr.find(qn("w:bottom"))
    if bottom is None:
        return None
    val = bottom.get(qn("w:val")) or "single"
    if val in {"nil", "none"}:
        return None
    try:
        sz = int(bottom.get(qn("w:sz")) or "2")
    except ValueError:
        sz = 2
    try:
        space = int(bottom.get(qn("w:space")) or "1")
    except ValueError:
        space = 1
    color = bottom.get(qn("w:color")) or "AAAAAA"
    return SeparatorStyle(enabled=True, val=val, sz=sz, space=space, color=color)


def _looks_like_section_heading(paragraph, *, body_size: int) -> bool:
    text = paragraph.text.strip()
    if not text or len(text) > 48 or "\n" in text:
        return False
    if _match_section_key(text):
        return True
    # Short bold / larger / ALL-CAPS lines are likely headings.
    # Require ALL-CAPS for non-alias matches so name/body lines (e.g. "Jane Doe")
    # are not stored as synthetic section keys that confuse generation.
    runs = [r for r in paragraph.runs if r.text and r.text.strip()]
    if not runs:
        return False
    boldish = any(bool(r.bold) for r in runs)
    sizes = []
    for run in runs:
        if run.font.size is not None:
            sizes.append(int(round(run.font.size.pt)))
    larger = any(s >= body_size + 1 for s in sizes)
    mostly_upper = text == text.upper() and any(c.isalpha() for c in text)
    word_count = len(text.split())
    return word_count <= 6 and mostly_upper and (boldish or larger)


def _extract_page_border(section) -> PageBorderStyle:
    try:
        from docx.oxml.ns import qn
    except ImportError:
        return PageBorderStyle(enabled=False)

    sect_pr = section._sectPr
    if sect_pr is None:
        return PageBorderStyle(enabled=False)
    pg_borders = sect_pr.find(qn("w:pgBorders"))
    if pg_borders is None:
        return PageBorderStyle(enabled=False)

    sides: list[str] = []
    sample = None
    for side in ("top", "left", "bottom", "right"):
        el = pg_borders.find(qn(f"w:{side}"))
        if el is None:
            continue
        val = el.get(qn("w:val")) or ""
        if val in {"", "nil", "none"}:
            continue
        sides.append(side)
        if sample is None:
            sample = el
    if not sides or sample is None:
        return PageBorderStyle(enabled=False)
    try:
        sz = int(sample.get(qn("w:sz")) or "4")
    except ValueError:
        sz = 4
    try:
        space = int(sample.get(qn("w:space")) or "24")
    except ValueError:
        space = 24
    return PageBorderStyle(
        enabled=True,
        val=sample.get(qn("w:val")) or "single",
        sz=sz,
        space=space,
        color=sample.get(qn("w:color")) or "000000",
        sides=tuple(sides),
    )


def _extract_experience_layout(document) -> ExperienceLayout:
    layout = ExperienceLayout()
    try:
        from docx.oxml.ns import qn
    except ImportError:
        return layout

    for table in document.tables:
        if len(table.columns) != 2 or not table.rows:
            continue
        row = table.rows[0]
        if len(row.cells) < 2:
            continue
        left_text = row.cells[0].text.strip()
        right_text = row.cells[1].text.strip()
        if not left_text:
            continue
        # Prefer tables that look like company | duration.
        looks_dated = bool(re.search(r"\d{4}|present|current", right_text, re.IGNORECASE))
        if not looks_dated and len(right_text) > 40:
            continue

        widths: list[float] = []
        for cell in row.cells[:2]:
            tc_pr = cell._tc.tcPr
            width_in = None
            if tc_pr is not None:
                tc_w = tc_pr.first_child_found_in("w:tcW")
                if tc_w is not None:
                    try:
                        width_in = int(tc_w.get(qn("w:w")) or "0") / 1440.0
                    except ValueError:
                        width_in = None
            widths.append(width_in if width_in and width_in > 0 else 0.0)

        if widths[0] > 0 and widths[1] > 0:
            layout.left_width_in = round(widths[0], 2)
            layout.right_width_in = round(widths[1], 2)
        layout.company_line_mode = "two_column_table"

        # Detect bold on left/right runs.
        left_bold = any(bool(r.bold) for p in row.cells[0].paragraphs for r in p.runs)
        right_bold = any(bool(r.bold) for p in row.cells[1].paragraphs for r in p.runs)
        layout.company_bold = left_bold if row.cells[0].paragraphs else True
        layout.duration_bold = right_bold if row.cells[1].paragraphs else True

        right_align = "right"
        for paragraph in row.cells[1].paragraphs:
            align = paragraph.alignment
            if align is not None:
                # WD_ALIGN_PARAGRAPH.RIGHT == 2
                right_align = "right" if int(align) == 2 else "left" if int(align) == 0 else "center"
                break
        layout.duration_align = right_align
        return layout

    # Fallback: pipe/tab single-line company layouts still use two-column emission.
    layout.company_line_mode = "two_column_table"
    return layout


def _extract_structure_from_document(document, *, body_size: int) -> DocumentStructure:
    structure = default_document_structure()
    sections: list[SectionRule] = []
    seen_keys: set[str] = set()
    separator: Optional[SeparatorStyle] = None
    pending_separator = False
    order = 0

    # Walk block items so we can associate separators with following headings.
    for block in document.element.body:
        tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag
        if tag != "p":
            continue
        # Resolve python-docx paragraph wrapper
        paragraph = None
        for candidate in document.paragraphs:
            if candidate._p is block:
                paragraph = candidate
                break
        if paragraph is None:
            continue

        if _paragraph_has_bottom_border(paragraph) and not paragraph.text.strip():
            pending_separator = True
            border = _read_bottom_border(paragraph)
            if border is not None:
                separator = border
            continue

        if not _looks_like_section_heading(paragraph, body_size=body_size):
            # A heading paragraph may itself carry a bottom border as the rule.
            if _paragraph_has_bottom_border(paragraph):
                border = _read_bottom_border(paragraph)
                if border is not None:
                    separator = border
            continue

        heading_text = paragraph.text.strip()
        key = _match_section_key(heading_text)
        if key is None:
            # Unknown heading — keep label under a synthetic key for persistence.
            # Generation remaps known phrases (e.g. professional_experience → experience).
            key = re.sub(r"[^a-z0-9]+", "_", heading_text.casefold()).strip("_") or f"section_{order}"
            key = canonicalize_section_key(key, heading_text)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        sections.append(
            SectionRule(
                key=key,
                heading=heading_text,
                separator_before=pending_separator or _paragraph_has_bottom_border(paragraph),
                order=order,
            )
        )
        order += 1
        pending_separator = False

        # Capture heading spacing from the first matched heading.
        if order == 1:
            pf = paragraph.paragraph_format
            before = pf.space_before.pt if pf.space_before is not None else structure.heading_style.space_before_pt
            after = pf.space_after.pt if pf.space_after is not None else structure.heading_style.space_after_pt
            run_list = list(paragraph.runs)
            bold = any(bool(r.bold) for r in run_list) if run_list else True
            alignment = "left"
            if paragraph.alignment is not None:
                align_map = {0: "left", 1: "center", 2: "right", 3: "justify"}
                alignment = align_map.get(int(paragraph.alignment), "left")
            structure.heading_style = HeadingStyle(
                bold=bool(bold),
                space_before_pt=float(before),
                space_after_pt=float(after),
                alignment=alignment,
            )

    if sections:
        # Fill in any missing canonical sections using default labels, appended.
        for default_sec in default_document_structure().sections:
            if default_sec.key not in seen_keys:
                sections.append(
                    SectionRule(
                        key=default_sec.key,
                        heading=default_sec.heading,
                        separator_before=True,
                        order=len(sections),
                    )
                )
        structure.sections = sections
    if separator is not None:
        structure.separator = separator
    elif any(s.separator_before for s in structure.sections):
        structure.separator = SeparatorStyle(enabled=True)
    else:
        structure.separator = SeparatorStyle(enabled=False)

    structure.experience = _extract_experience_layout(document)
    if document.sections:
        structure.page_border = _extract_page_border(document.sections[0])
    return structure


def _effective_run_font_name(run) -> Optional[str]:
    """Return the concrete font name on a run, including theme/ascii fallbacks."""
    name = run.font.name
    if name:
        return name
    try:
        from docx.oxml.ns import qn

        r_pr = run._element.rPr
        if r_pr is None:
            return None
        r_fonts = r_pr.rFonts
        if r_fonts is None:
            return None
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            value = r_fonts.get(qn(attr))
            if value:
                return value
    except Exception:
        return None
    return None


def extract_format_from_docx(docx_path: str | Path, *, name: str = "") -> ResumeFormatSpec:
    """Inspect a .docx and build a ResumeFormatSpec (not yet saved).

    Extracts page size/margins, typography hints, and structural rules
    (section headings, separators, experience layout, page borders).
    Missing values fall back to defaults.
    """
    path = Path(docx_path).expanduser()
    if not path.is_file():
        raise FormatValidationError(f"File not found: {path}")
    if path.suffix.casefold() != ".docx":
        raise FormatValidationError("Only .docx files are supported for format upload")

    try:
        from docx import Document
    except ImportError as exc:
        raise FormatValidationError(
            "python-docx is required. Run: python3 -m pip install -r requirements.txt"
        ) from exc

    document = Document(str(path))
    section = document.sections[0]

    def inches(value: Any, default: float) -> float:
        try:
            return round(float(value) / 914400, 4)  # EMUs → inches
        except Exception:
            return default

    font_name: Optional[str] = None
    body_size = DEFAULT_FORMAT_VALUES["body_size"]
    name_size = DEFAULT_FORMAT_VALUES["name_size"]
    heading_size = DEFAULT_FORMAT_VALUES["heading_size"]

    try:
        normal = document.styles["Normal"]
        if normal.font.name:
            font_name = normal.font.name
        if normal.font.size is not None:
            body_size = int(round(normal.font.size.pt))
    except Exception:
        pass

    # Scan early runs for fonts and sizes. Real run fonts must win over the
    # default / Normal fallback (previously `font_name = font_name or run.font.name`
    # left Arial stuck once the default was assigned).
    sizes: list[int] = []
    bold_sizes: list[int] = []
    run_fonts: list[str] = []
    for paragraph in document.paragraphs[:80]:
        for run in paragraph.runs:
            run_font = _effective_run_font_name(run)
            if run_font:
                run_fonts.append(run_font)
                font_name = run_font
            if run.font.size is not None:
                pt = int(round(run.font.size.pt))
                sizes.append(pt)
                if run.bold:
                    bold_sizes.append(pt)

    if run_fonts:
        # Prefer the most common explicit run font.
        font_name = max(set(run_fonts), key=run_fonts.count)

    if bold_sizes:
        name_size = max(bold_sizes)
    if sizes:
        above_body = [s for s in sizes if s > body_size]
        if above_body:
            heading_size = sorted(above_body)[len(above_body) // 2]
        if not bold_sizes:
            name_size = max(sizes)

    structure = _extract_structure_from_document(document, body_size=body_size)

    # Infer line spacing from Normal style when available.
    line_spacing = DEFAULT_FORMAT_VALUES["line_spacing"]
    try:
        normal = document.styles["Normal"]
        if normal.paragraph_format.line_spacing is not None:
            line_spacing = float(normal.paragraph_format.line_spacing)
    except Exception:
        pass

    display_name = name.strip() or path.stem
    return ResumeFormatSpec(
        id=_new_format_id(display_name),
        name=display_name,
        font_name=font_name or DEFAULT_FORMAT_VALUES["font_name"],
        name_size=name_size,
        heading_size=heading_size,
        body_size=body_size,
        page_width_in=inches(section.page_width, DEFAULT_FORMAT_VALUES["page_width_in"]),
        page_height_in=inches(section.page_height, DEFAULT_FORMAT_VALUES["page_height_in"]),
        margin_top_in=inches(section.top_margin, DEFAULT_FORMAT_VALUES["margin_top_in"]),
        margin_right_in=inches(section.right_margin, DEFAULT_FORMAT_VALUES["margin_right_in"]),
        margin_bottom_in=inches(section.bottom_margin, DEFAULT_FORMAT_VALUES["margin_bottom_in"]),
        margin_left_in=inches(section.left_margin, DEFAULT_FORMAT_VALUES["margin_left_in"]),
        header_distance_in=inches(section.header_distance, DEFAULT_FORMAT_VALUES["header_distance_in"]),
        footer_distance_in=inches(section.footer_distance, DEFAULT_FORMAT_VALUES["footer_distance_in"]),
        line_spacing=line_spacing,
        structure=structure,
        protected=False,
        source="docx",
    )


def add_format_from_docx(
    username: str,
    docx_path: str | Path,
    name: str,
    *,
    set_as_primary: bool = False,
) -> ResumeFormatSpec:
    """Add Format flow: extract structure from a Word file and save under ``name``."""
    extracted = extract_format_from_docx(docx_path, name=name)
    return create_format(
        username,
        name,
        xml_text=format_spec_to_xml(extracted),
        source="docx",
        set_as_primary=set_as_primary,
    )


def get_format_for_writer(username: Optional[str] = None) -> ResumeFormatSpec:
    """Resolve the format the writer should use.

    - Signed-in user → primary format (fallback to default if missing)
    - No user → protected default application format
    """
    if not username:
        return default_format_spec()
    try:
        return get_primary_format(username)
    except Exception:
        return default_format_spec()
