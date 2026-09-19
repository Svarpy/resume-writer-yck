"""Per-user resume format store (XML) plus the protected application default.

The built-in ``default`` format mirrors the historical hardcoded layout in
``resume_writer_app.ResumeFormat`` / ``apply_document_defaults``. It is always
listed, cannot be edited or deleted, and is the fallback when no primary is set.
"""

from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Optional
from xml.dom import minidom

from app_paths import sanitize_username, user_formats_dir
from user_auth import get_profile, update_profile

DEFAULT_FORMAT_ID = "default"
DEFAULT_FORMAT_NAME = "Default Application Format"

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


class FormatError(Exception):
    """Base class for format-store errors."""


class FormatNotFoundError(FormatError):
    pass


class FormatProtectedError(FormatError):
    pass


class FormatValidationError(FormatError):
    pass


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
    protected: bool = False
    source: str = "manual"  # manual | docx | default

    def to_writer_kwargs(self) -> dict[str, Any]:
        """Subset accepted by ``resume_writer_app.ResumeFormat``."""
        return {
            "font_name": self.font_name,
            "name_size": int(self.name_size),
            "heading_size": int(self.heading_size),
            "body_size": int(self.body_size),
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
        }


def default_format_spec() -> ResumeFormatSpec:
    return ResumeFormatSpec(
        id=DEFAULT_FORMAT_ID,
        name=DEFAULT_FORMAT_NAME,
        protected=True,
        source="default",
        **{k: v for k, v in DEFAULT_FORMAT_VALUES.items()},
    )


def _slugify_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "format"


def _new_format_id(name: str) -> str:
    return f"{_slugify_name(name)}-{uuid.uuid4().hex[:8]}"


def _format_path(username: str, format_id: str) -> Path:
    if format_id == DEFAULT_FORMAT_ID:
        raise FormatProtectedError("Default format is not stored as a user file")
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", format_id.strip())
    if not safe_id or safe_id == DEFAULT_FORMAT_ID:
        raise FormatValidationError("Invalid format id")
    return user_formats_dir(username) / f"{safe_id}.xml"


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


def format_spec_to_xml(spec: ResumeFormatSpec) -> str:
    root = ET.Element("resumeFormat", {"version": "1", "id": spec.id})
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

    rough = ET.tostring(root, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")
    # minidom adds an XML declaration; return decoded string.
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
    )


def default_format_xml() -> str:
    return format_spec_to_xml(default_format_spec())


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
        # Keep only known fields.
        allowed = {f.name for f in fields(ResumeFormatSpec)}
        payload = {k: v for k, v in payload.items() if k in allowed}
        spec = ResumeFormatSpec(**payload)

    spec.protected = False
    spec.source = source
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
        allowed = {f.name for f in fields(ResumeFormatSpec)}
        payload = {k: v for k, v in payload.items() if k in allowed}
        updated = ResumeFormatSpec(**payload)

    updated.protected = False
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


def extract_format_from_docx(docx_path: str | Path, *, name: str = "") -> ResumeFormatSpec:
    """Inspect a .docx and build a ResumeFormatSpec (not yet saved).

    Extracts page size/margins from the first section and typography hints from
    document styles / early paragraphs. Missing values fall back to defaults.
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

    font_name = DEFAULT_FORMAT_VALUES["font_name"]
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

    # Scan early runs for the largest bold size (likely the name) and mid sizes (headings).
    sizes: list[int] = []
    bold_sizes: list[int] = []
    for paragraph in document.paragraphs[:40]:
        for run in paragraph.runs:
            if run.font.name:
                font_name = font_name or run.font.name
            if run.font.size is not None:
                pt = int(round(run.font.size.pt))
                sizes.append(pt)
                if run.bold:
                    bold_sizes.append(pt)

    if bold_sizes:
        name_size = max(bold_sizes)
    if sizes:
        # Heading ≈ median of sizes above body; body ≈ most common / Normal.
        above_body = [s for s in sizes if s > body_size]
        if above_body:
            heading_size = sorted(above_body)[len(above_body) // 2]
        if not bold_sizes:
            name_size = max(sizes)

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
        line_spacing=DEFAULT_FORMAT_VALUES["line_spacing"],
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
