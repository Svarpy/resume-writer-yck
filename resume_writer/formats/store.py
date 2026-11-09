"""Per-user format XML persistence and CRUD."""

from __future__ import annotations

import re
import shutil
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Optional
from xml.dom import minidom

from resume_writer.paths import sanitize_username, user_formats_dir
from resume_writer.auth.service import get_profile, update_profile
from resume_writer.formats.models import (
    DEFAULT_FORMAT_ID,
    DEFAULT_FORMAT_NAME,
    DEFAULT_FORMAT_VALUES,
    FORMAT_XML_VERSION,
    DocumentStructure,
    ExperienceLayout,
    FormatError,
    FormatNotFoundError,
    FormatProtectedError,
    FormatValidationError,
    HeadingStyle,
    PageBorderStyle,
    ResumeFormatSpec,
    SectionRule,
    SeparatorStyle,
    canonicalize_section_key,
    default_document_structure,
    default_format_spec,
    normalize_line_spacing,
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
    ET.SubElement(exp, "tabPosTwips").text = str(int(structure.experience.tab_pos_twips))
    ET.SubElement(exp, "companyBold").text = "true" if structure.experience.company_bold else "false"
    ET.SubElement(exp, "durationBold").text = "true" if structure.experience.duration_bold else "false"
    ET.SubElement(exp, "durationAlign").text = structure.experience.duration_align
    ET.SubElement(exp, "roleBelowCompany").text = "true" if structure.experience.role_below_company else "false"
    ET.SubElement(exp, "bulletsUnderRole").text = "true" if structure.experience.bullets_under_role else "false"
    ET.SubElement(exp, "bulletMarker").text = structure.experience.bullet_marker

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
        tab_pos_twips=_require_int(_text(exp_el, "tabPosTwips", str(base.experience.tab_pos_twips)), "tabPosTwips")
        if exp_el is not None
        else base.experience.tab_pos_twips,
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
        bullet_marker=(
            (_text(exp_el, "bulletMarker", base.experience.bullet_marker) or base.experience.bullet_marker)
            if exp_el is not None
            else base.experience.bullet_marker
        ),
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
        line_spacing = normalize_line_spacing(
            _require_float(_text(spacing, "lineSpacing", str(line_spacing)), "lineSpacing")
        )

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
    if not updated.template_file and existing.template_file:
        updated.template_file = existing.template_file
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

    try:
        existing = _read_user_format(key, format_id)
        template_path = resolve_format_template_path(key, existing)
        if template_path is not None and template_path.is_file():
            template_path.unlink()
    except FormatError:
        pass
    conventional = format_template_path(key, format_id)
    if conventional.is_file():
        conventional.unlink()

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

