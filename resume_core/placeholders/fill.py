"""Filling a template with data: repeat blocks, replace fields, drop what is empty.

Everything here is mechanical. A block ``{{#x}} ... {{/x}}`` is repeated once per item of ``x`` (and left
out when there is none); a field ``{{y}}`` becomes its value, looked up from the innermost block outwards.
An empty field disappears together with the fixed text (a separator such as " | ", a label such as
"GPA: ") that only existed to introduce it.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from resume_core.ooxml.xmlutil import (
    P,
    R,
    RPR,
    T,
    TAB,
    BR,
    TBL,
    TC,
    TR,
    iter_paragraphs,
    paragraph_text,
    replace_span,
)
from resume_core.placeholders.info import TemplateError, inspect_document
from resume_core.placeholders.scan import (
    all_tokens,
    block_range,
    pair_blocks,
    paragraph_tokens,
    siblings,
    token_of_run,
)

_SYMBOL_FONTS = {"symbol", "wingdings", "wingdings 2", "wingdings 3", "webdings"}
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


class _Scope:
    """Data visible at some point of the template: innermost block first, then the ones around it."""

    def __init__(self, stack: list[dict[str, Any]]) -> None:
        self.stack = stack

    def push(self, item: dict[str, Any]) -> "_Scope":
        return _Scope([*self.stack, item])

    def get(self, name: str) -> Any:
        for layer in reversed(self.stack):
            if name in layer:
                return layer[name]
        return None


def _items(value: Any) -> list[dict[str, Any]]:
    if value is None or value is False or value == "" or value == []:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, (list, tuple)):
        return [v if isinstance(v, dict) else {"text": str(v)} for v in value if v not in (None, "")]
    return [{"text": str(value)}]


def _tokens_in(elements) -> list:
    out = []
    for element in elements:
        for paragraph in ([element] if element.tag == P else element.iter(P)):
            out.extend(paragraph_tokens(paragraph))
    return out


def _blank(paragraph) -> bool:
    return not paragraph_text(paragraph).strip() and not paragraph.findall(".//" + qn("w:drawing"))


class _Filler:
    def __init__(self, document, data: dict[str, Any], font_name: str, sizes: dict[str, int],
                 headings: Optional[dict[str, tuple[str, bool]]] = None) -> None:
        self.document = document
        self.headings = headings or {}      # section key -> (heading text, shown) chosen in Settings
        self.data = data
        self.font_name = font_name
        self.sizes = sizes
        self.heading_paragraphs: list = []   # element references (lxml proxies have no stable id())
        self.name_paragraph = None
        self.contact_runs: list[tuple[object, str, str]] = []   # (run, kind, value)

    # ------------------------------------------------------------------ driver
    def run(self) -> None:
        body = self.document.element.body
        for token in all_tokens(body):
            if token.kind == "field" and token.name == "name":
                if paragraph_text(token.paragraph).strip() == "{{name}}":
                    self.name_paragraph = token.paragraph
        begin, end = OxmlElement("w:p"), OxmlElement("w:p")
        first = next((c for c in body if c.tag != qn("w:sectPr")), None)
        last = [c for c in body if c.tag != qn("w:sectPr")][-1]
        first.addprevious(begin)
        last.addnext(end)
        self._expand(body, begin, end, _Scope([self.data]), top=True)
        body.remove(begin)
        body.remove(end)
        self._link_contacts()
        self._apply_typography()

    # ------------------------------------------------------------------ blocks
    def _between(self, begin, end) -> list:
        out = []
        node = begin.getnext()
        while node is not None and node is not end:
            out.append(node)
            node = node.getnext()
        return out

    def _expand(self, parent, begin, end, scope: _Scope, top: bool = False) -> None:
        for _ in range(10_000):
            elements = self._between(begin, end)
            blocks = [b for b in pair_blocks(_tokens_in(elements)) if b.parent is None]
            if not blocks:
                break
            self._expand_block(blocks[0], scope, top)
        self._substitute(self._between(begin, end), scope)

    def _expand_block(self, block, scope: _Scope, top: bool) -> None:
        container, first, last = block_range(block)
        originals = list(siblings(first, last))
        items = _items(scope.get(block.name))
        anchor = first
        count = len(items)
        for position, item in enumerate(items):
            begin, end = OxmlElement("w:p"), OxmlElement("w:p")
            copies = [deepcopy(e) for e in originals]
            self._strip_own_markers(copies, block.name)
            if position == count - 1:
                self._drop_trailing_spacer(copies)
            for element in (begin, *copies, end):
                anchor.addprevious(element)
            if top and position == 0:
                self._note_heading(copies, block.name)
            self._expand(container, begin, end, scope.push(item))
            container.remove(begin)
            container.remove(end)
        for element in originals:
            if element.getparent() is container:
                container.remove(element)
        if container.tag == TC and not [c for c in container if c.tag in (P, TBL)]:
            container.append(OxmlElement("w:p"))

    @staticmethod
    def _strip_own_markers(copies: list, name: str) -> None:
        tokens = _tokens_in(copies)
        start = next((t for t in tokens if t.kind == "start" and t.name == name), None)
        end = next((t for t in reversed(tokens) if t.kind == "end" and t.name == name), None)
        for token in (start, end):
            if token is not None and token.run.getparent() is not None:
                token.run.getparent().remove(token.run)

    @staticmethod
    def _drop_trailing_spacer(copies: list) -> None:
        """A blank paragraph that only separates repeated units is not wanted after the last one."""
        if len(copies) > 1 and copies[-1].tag == P and _blank(copies[-1]) and not _tokens_in(copies[-1:]):
            copies.pop()

    def _note_heading(self, copies: list, key: str) -> None:
        """Find the section's heading paragraph (for the heading font size) and apply a Settings override."""
        for element in copies:
            for paragraph in ([element] if element.tag == P else element.iter(P)):
                if any(t.kind == "field" for t in paragraph_tokens(paragraph)):
                    return
                text = paragraph_text(paragraph)
                if not any(ch.isalpha() for ch in text):
                    continue
                wanted, shown = self.headings.get(key, ("", True))
                if not shown:
                    paragraph.getparent().remove(paragraph)
                    return
                if wanted and wanted != text.strip():
                    start = len(text) - len(text.lstrip())
                    replace_span(paragraph, start, len(text.rstrip(" \t\n\u00a0")), wanted)
                self.heading_paragraphs.append(paragraph)
                return

    # ------------------------------------------------------------------ fields
    def _substitute(self, elements: list, scope: _Scope) -> None:
        paragraphs = []
        for element in elements:
            paragraphs.extend([element] if element.tag == P else element.iter(P))
        doomed = []
        for paragraph in paragraphs:
            if self._fill_paragraph(paragraph, scope):
                doomed.append(paragraph)
        for paragraph in doomed:
            self._remove_paragraph(paragraph)

    def _fill_paragraph(self, paragraph, scope: _Scope) -> bool:
        """Fill the paragraph's fields. Returns True when it had fields and every one was empty."""
        segments = []        # (kind, run, value)
        for run in paragraph.iter(R):
            found = token_of_run(run)
            if found and found[0] == "field":
                value = scope.get(found[1])
                segments.append(("F", run, "" if value is None else str(value).strip(), found[1]))
            elif any(c.tag in (T, TAB, BR) for c in run):
                segments.append(("L", run, "", ""))
        fields = [s for s in segments if s[0] == "F"]
        if not fields:
            return False
        removals: set[int] = set()
        seen_visible = False
        pending: list = []            # literal runs since the previous field
        for index, (kind, run, value, _name) in enumerate(segments):
            if kind == "L":
                pending.append(run)
                continue
            if value:
                seen_visible = True
                pending = []
                continue
            removals.add(id(run))
            if seen_visible:
                removals.update(id(r) for r in pending)       # " | ", " – ", "  |  GPA: " ...
            else:
                nxt = []
                for later in segments[index + 1:]:
                    if later[0] != "L":
                        break
                    nxt.append(later[1])
                removals.update(id(r) for r in nxt)             # a leading empty field drops its separator after
            pending = []
        for kind, run, value, name in segments:
            if kind != "F" or id(run) in removals:
                continue
            node = next(c for c in run if c.tag == T)
            node.text = value
            node.set(_XML_SPACE, "preserve")
            if name in ("email", "phone"):
                self.contact_runs.append((run, name, value))
        for kind, run, value, name in segments:
            if id(run) in removals and run.getparent() is not None:
                run.getparent().remove(run)
        return not any(s[2] for s in fields)

    @staticmethod
    def _remove_paragraph(paragraph) -> None:
        parent = paragraph.getparent()
        if parent is None:
            return
        if parent.tag == TC and len([c for c in parent if c.tag == P]) == 1 and not parent.findall(TBL):
            row = parent.getparent()
            table = row.getparent() if row is not None else None
            if row is not None and table is not None and row.tag == TR and all(
                    not paragraph_text(p).strip() for p in row.iter(P)):
                table.remove(row)                         # a row whose cells are all empty goes away
                if not table.findall(TR) and table.getparent() is not None:
                    table.getparent().remove(table)
            return
        parent.remove(paragraph)

    # ------------------------------------------------------------------ links
    def _link_contacts(self) -> None:
        """Email and phone become mailto: / tel: hyperlinks (the run keeps the template's look)."""
        rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
        for run, kind, value in self.contact_runs:
            if run.getparent() is None or not value or run.getparent().tag == qn("w:hyperlink"):
                continue
            url = f"mailto:{value}" if kind == "email" else "tel:" + "".join(
                ch for ch in value if ch.isdigit() or ch == "+")
            link = OxmlElement("w:hyperlink")
            link.set(qn("r:id"), self.document.part.relate_to(url, rel_type, is_external=True))
            run.addprevious(link)
            link.append(run)

    # ------------------------------------------------------------------ typography
    def _apply_typography(self) -> None:
        """Give the name, headings and all other text exactly the font and sizes chosen in the Writer."""
        font = (self.font_name or "").strip()
        sizes = {k: v * 2 for k, v in self.sizes.items()}
        if not font and not any(sizes.values()):
            return
        for paragraph in iter_paragraphs(self.document.element.body):
            if paragraph is self.name_paragraph:
                group = "name"
            elif any(paragraph is heading for heading in self.heading_paragraphs):
                group = "heading"
            else:
                group = "body"
            targets = []
            for run in paragraph.iter(R):
                rpr = run.find(RPR)
                if rpr is None:
                    rpr = OxmlElement("w:rPr")
                    run.insert(0, rpr)
                targets.append(rpr)
            targets.append(self._paragraph_mark_rpr(paragraph))
            for rpr in targets:
                self._style_rpr(rpr, font, sizes.get(group, 0))

    @staticmethod
    def _paragraph_mark_rpr(paragraph):
        ppr = paragraph.find(qn("w:pPr"))
        if ppr is None:
            ppr = OxmlElement("w:pPr")
            paragraph.insert(0, ppr)
        rpr = ppr.find(RPR)
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            anchor = next((c for c in ppr if c.tag in (qn("w:sectPr"), qn("w:pPrChange"))), None)
            if anchor is not None:
                anchor.addprevious(rpr)
            else:
                ppr.append(rpr)
        return rpr

    @staticmethod
    def _style_rpr(rpr, font: str, size_half_points: int) -> None:
        fonts = rpr.find(qn("w:rFonts"))
        current = (fonts.get(qn("w:ascii")) or "").casefold() if fonts is not None else ""
        if font and current not in _SYMBOL_FONTS:
            if fonts is None:
                fonts = OxmlElement("w:rFonts")
                _insert_in_order(rpr, fonts)
            for attribute in list(fonts.attrib):
                del fonts.attrib[attribute]
            for attribute in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                fonts.set(qn(attribute), font)
        if size_half_points:
            for tag in ("w:sz", "w:szCs"):
                node = rpr.find(qn(tag))
                if node is None:
                    node = OxmlElement(tag)
                    _insert_in_order(rpr, node)
                node.set(qn("w:val"), str(size_half_points))


_RPR_ORDER = (
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline", "shadow",
    "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
    "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs",
    "em", "lang", "eastAsianLayout", "specVanish", "oMath",
)


def _insert_in_order(rpr, element) -> None:
    name = element.tag.split("}")[1]
    rank = _RPR_ORDER.index(name) if name in _RPR_ORDER else len(_RPR_ORDER)
    for child in rpr:
        child_name = child.tag.split("}")[1]
        if (_RPR_ORDER.index(child_name) if child_name in _RPR_ORDER else len(_RPR_ORDER)) > rank:
            child.addprevious(element)
            return
    rpr.append(element)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def fill_template(template_path: Path, data: dict[str, Any], output_path: Path, *, font_name: str = "",
                  name_size: int = 0, heading_size: int = 0, body_size: int = 0,
                  properties: Optional[dict[str, str]] = None,
                  headings: Optional[dict[str, tuple[str, bool]]] = None) -> Path:
    """Write ``data`` into a copy of the template ``.docx`` and save it to ``output_path``."""
    from docx import Document

    template_path = Path(template_path)
    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found: {template_path}")
    document = Document(str(template_path))
    info = inspect_document(document)          # also normalises the markers in place
    if not info.ok:
        raise TemplateError("The template has problems: " + "; ".join(info.errors))
    _Filler(document, data, font_name, {"name": name_size, "heading": heading_size, "body": body_size},
            headings).run()
    core = document.core_properties
    for key, value in (properties or {}).items():       # author, subject, title, keywords, last_modified_by
        setattr(core, key, value)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _drop_unused_hyperlink_rels(document)
    document.save(output_path)
    return output_path


def _drop_unused_hyperlink_rels(document) -> None:
    """Remove external hyperlink relationships nothing refers to any more (they would keep old addresses)."""
    used = {node.get(qn("r:id")) for node in document.element.iter(qn("w:hyperlink")) if node.get(qn("r:id"))}
    for rel_id, rel in list(document.part.rels.items()):
        if rel.is_external and rel.reltype.endswith("/hyperlink") and rel_id not in used:
            document.part.rels.pop(rel_id)
