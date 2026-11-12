"""Reading a template: its sections, the fields each section can show, typography, and mistakes."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from resume_core.ooxml.styles import StyleSheet
from resume_core.ooxml.xmlutil import P, iter_paragraphs, paragraph_text
from resume_core.placeholders.scan import (
    BLOCK_FIELDS,
    INNER_BLOCKS,
    TOKEN_RE,
    ROOT_FIELDS,
    Block,
    all_tokens,
    block_range,
    normalize,
    pair_blocks,
    paragraph_tokens,
    siblings,
)

CANONICAL_LABELS = {"summary": "Summary", "skills": "Skills", "experience": "Work Experience",
                    "education": "Education"}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")


class TemplateError(ValueError):
    """The uploaded document cannot be used as a resume template."""


@dataclass
class TemplateInfo:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)   # settings-style rows
    outline: list[str] = field(default_factory=list)
    shape: dict[str, dict[str, Any]] = field(default_factory=dict)  # key -> {kind, fields: {block: (fields)}}
    font_name: str = ""
    name_size: int = 0
    heading_size: int = 0
    body_size: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def _label(name: str, heading: str) -> str:
    if name in CANONICAL_LABELS:
        return CANONICAL_LABELS[name]
    return (heading.title() if heading.isupper() else heading) or name.replace("_", " ").title()


def _kind(block: Block) -> str:
    names = {c.name: c for c in block.children}
    if "jobs" in names:
        return "experience"
    if "degrees" in names:
        return "education"
    if "items" in names:
        items = names["items"].fields
        return "skills" if "label" in items or "values" in items else "bullets"
    return "paragraph"


def _describe(block: Block) -> str:
    direct = ", ".join(dict.fromkeys(block.fields))
    parts = [f"{block.name}({direct})" if direct and block.depth else block.name]
    if direct and not block.depth:
        parts.append(direct)
    kids = [_describe(c) for c in block.children]
    if kids:
        parts.append(" + ".join(kids))
    return " > ".join(parts)


def _collect_fields(block: Block, out: dict[str, tuple]) -> None:
    for child in block.children:
        out[child.name] = tuple(dict.fromkeys(child.fields))
        _collect_fields(child, out)


def _literal_text(paragraph) -> str:
    return TOKEN_RE.sub("", paragraph_text(paragraph)).strip(" \t\n\u00a0")


def _heading_paragraph(block: Block):
    """First paragraph of a section that is only fixed text (the section heading), if any."""
    container, first, last = block_range(block)
    if container is None:
        return None
    for element in siblings(first, last):
        for paragraph in ([element] if element.tag == P else list(iter_paragraphs(element))):
            if any(t.kind == "field" for t in paragraph_tokens(paragraph)):
                return None
            if re.search(r"[^\W\d_]", _literal_text(paragraph)):
                return paragraph
    return None


def inspect_document(document) -> TemplateInfo:
    """Normalise ``document`` in place and describe it. ``document`` is a python-docx Document."""
    info = TemplateInfo()
    body = document.element.body
    normalize(body)
    tokens = all_tokens(body)
    if not tokens:
        info.errors.append("The document has no {{placeholders}}. Upload a parsed template, not the plain sample.")
        return info
    blocks = pair_blocks(tokens, info.errors)
    tops = [b for b in blocks if b.parent is None]
    by_start = {id(b.start): b for b in blocks}

    # fields: who is where
    owner: dict[int, Optional[Block]] = {}
    stack: list[Block] = []
    for token in tokens:
        if token.kind == "start" and id(token) in by_start:
            stack.append(by_start[id(token)])
        elif token.kind == "end" and stack and stack[-1].end is token:
            stack.pop()
        elif token.kind == "field":
            owner[id(token)] = stack[-1] if stack else None
    for token in tokens:
        if token.kind != "field":
            continue
        inside = owner.get(id(token))
        known = BLOCK_FIELDS + ROOT_FIELDS if inside else ROOT_FIELDS
        if token.name not in known:
            if inside is None and token.name in BLOCK_FIELDS:
                info.errors.append(f"{{{{{token.name}}}}} is used outside any block")
            else:
                info.errors.append(f"unknown field {{{{{token.name}}}}}")
    for block in blocks:
        if block.parent is not None and block.name not in INNER_BLOCKS:
            info.errors.append(f"unknown block {{{{#{block.name}}}}} inside {{{{#{block.parent.name}}}}} "
                               f"(use one of: {', '.join(INNER_BLOCKS)})")
        container, first, last = block_range(block)
        if container is None:
            info.errors.append(f"{{{{#{block.name}}}}} and {{{{/{block.name}}}}} are not in the same body or table cell")
            continue
        if not any(el is last for el in siblings(first, last)):
            info.errors.append(f"{{{{/{block.name}}}}} comes before {{{{#{block.name}}}}}")
    names = [b.name for b in tops]
    for name in dict.fromkeys(names):
        if names.count(name) > 1:
            info.errors.append(f"section {{{{#{name}}}}} appears more than once")
    if not tops:
        info.errors.append("The template has no section blocks ({{#summary}} ... {{/summary}}).")

    # sections, outline, shape
    sheet = StyleSheet(document)
    headings = []
    for block in tops:
        kind = _kind(block)
        heading_p = _heading_paragraph(block)
        heading = _literal_text(heading_p) if heading_p is not None else ""
        if heading_p is not None:
            headings.append(heading_p)
        fields: dict[str, tuple] = {}
        _collect_fields(block, fields)
        if block.fields:
            fields[block.name] = tuple(dict.fromkeys(block.fields))
        shape = {"kind": kind, "fields": fields}
        grade = next((t for t in tokens if t.kind == "field" and t.name == "grade"
                      and block.start.index < t.index < block.end.index), None)
        if grade is not None:
            before = paragraph_text(grade.paragraph).split("{{grade}}")[0]
            shape["grade_label"] = before.rstrip().endswith(":")
        info.shape[block.name] = shape
        info.sections.append({
            "key": block.name, "label": _label(block.name, heading), "heading": heading, "kind": kind,
            "width": "full" if kind in ("experience", "paragraph") else "half", "enabled": True,
            "show_heading": bool(heading), "min_words": 0, "max_words": 0,
        })
        info.outline.append(_describe(block))
    root_fields = [t.name for t in tokens if t.kind == "field" and owner.get(id(t)) is None]
    if root_fields:
        info.outline.insert(0, ", ".join(dict.fromkeys(root_fields)))
    if "name" not in root_fields:
        info.warnings.append("The template has no {{name}} placeholder.")

    # typography of the template itself
    name_p = next((t.paragraph for t in tokens if t.kind == "field" and t.name == "name"
                   and not owner.get(id(t))), None)
    body_sizes: dict[int, int] = {}
    fonts: dict[str, int] = {}
    heading_ids = {id(p) for p in headings}
    for paragraph in iter_paragraphs(body):
        text = paragraph_text(paragraph)
        if not text.strip():
            continue
        fmt = sheet.dominant_format(paragraph)
        if fmt.font:
            fonts[fmt.font] = fonts.get(fmt.font, 0) + len(text)
        if paragraph is name_p or id(paragraph) in heading_ids:
            continue
        if fmt.size_half_pts:
            body_sizes[fmt.size_half_pts] = body_sizes.get(fmt.size_half_pts, 0) + len(text)
    info.font_name = max(fonts, key=fonts.get) if fonts else "Arial"
    half = max(body_sizes, key=body_sizes.get) if body_sizes else 22
    info.body_size = round(half / 2 + 0.01)
    info.name_size = round(sheet.dominant_format(name_p).size_half_pts / 2) if name_p is not None and \
        sheet.dominant_format(name_p).size_half_pts else 16
    info.heading_size = round(sheet.dominant_format(headings[0]).size_half_pts / 2) if headings and \
        sheet.dominant_format(headings[0]).size_half_pts else max(info.body_size, 12)

    # leftovers
    text = "\n".join(paragraph_text(p) for p in iter_paragraphs(body))
    if _EMAIL.search(text) or _PHONE.search(text):
        info.warnings.append("The template still contains an email address or phone number.")
    if body.findall(".//" + "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hyperlink"):
        info.warnings.append("The template contains hyperlinks; the app creates email and phone links itself.")
    return info


def inspect_template(data: bytes) -> TemplateInfo:
    """Describe an uploaded ``.docx`` template (raises ``TemplateError`` when it is not a Word file)."""
    from docx import Document

    if data[:2] != b"PK":
        raise TemplateError("Only .docx Word documents can be used as a resume format.")
    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - corrupt or unsupported packages
        raise TemplateError(f"Could not read the Word document: {exc}") from exc
    return inspect_document(document)
