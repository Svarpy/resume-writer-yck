"""Low-level WordprocessingML helpers: paragraph text, text-span replacement, containers.

Everything here works on lxml elements (python-docx's ``document.element``) so the
parser and generator never go through python-docx's higher-level objects, which
hide the details needed to reproduce a sample document exactly.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Iterator, NamedTuple, Optional

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

P = qn("w:p")
TBL = qn("w:tbl")
TR = qn("w:tr")
TC = qn("w:tc")
R = qn("w:r")
T = qn("w:t")
TAB = qn("w:tab")
BR = qn("w:br")
PPR = qn("w:pPr")
RPR = qn("w:rPr")
HYPERLINK = qn("w:hyperlink")
SDT = qn("w:sdt")
SDT_CONTENT = qn("w:sdtContent")

# Wrappers whose children are still part of the paragraph's own text flow.
_FLOW_WRAPPERS = {
    qn("w:hyperlink"), qn("w:ins"), qn("w:smartTag"), qn("w:sdt"), qn("w:sdtContent"),
    qn("w:fldSimple"), qn("w:customXml"),
}
# Never descend into these: they carry text that is not part of the line.
_SKIPPED = {qn("w:del"), qn("w:drawing"), qn("w:pict"), qn("w:object")}


class TextItem(NamedTuple):
    kind: str            # "t" | "tab" | "br"
    element: object      # the w:t / w:tab / w:br element
    run: object          # its w:r
    start: int
    end: int


def _walk_run_content(parent) -> Iterator[tuple[str, object, object]]:
    for child in parent:
        tag = child.tag
        if tag == R:
            for item in child:
                if item.tag == T:
                    yield "t", item, child
                elif item.tag == TAB:
                    yield "tab", item, child
                elif item.tag == BR:
                    yield "br", item, child
        elif tag in _SKIPPED:
            continue
        elif tag in _FLOW_WRAPPERS:
            inner = child.find(SDT_CONTENT) if tag == SDT else child
            if inner is not None:
                yield from _walk_run_content(inner)


def text_items(paragraph) -> list[TextItem]:
    """Text-bearing pieces of a paragraph in order, with their character offsets."""
    items: list[TextItem] = []
    pos = 0
    for kind, element, run in _walk_run_content(paragraph):
        length = len(element.text or "") if kind == "t" else 1
        items.append(TextItem(kind, element, run, pos, pos + length))
        pos += length
    return items


def paragraph_text(paragraph) -> str:
    out = []
    for item in text_items(paragraph):
        if item.kind == "t":
            out.append(item.element.text or "")
        elif item.kind == "tab":
            out.append("\t")
        else:
            out.append("\n")
    return "".join(out)


def _set_text(node, text: str) -> None:
    node.text = text
    node.set(XML_SPACE, "preserve")


def _drop_if_empty_run(run) -> None:
    """Remove a run left without content (keeps Word's XML tidy)."""
    if run is None or run.getparent() is None:
        return
    if all(child.tag == RPR for child in run):
        run.getparent().remove(run)


def _new_run_like(paragraph, model_run=None):
    run = OxmlElement("w:r")
    source = None
    if model_run is not None:
        source = model_run.find(RPR)
    if source is None:
        ppr = paragraph.find(PPR)
        if ppr is not None:
            source = ppr.find(RPR)  # paragraph-mark run properties
    if source is not None:
        run.append(deepcopy(source))
    return run


def replace_span(paragraph, start: int, end: int, new_text: str) -> None:
    """Replace characters ``[start, end)`` of the paragraph's text with ``new_text``.

    Run formatting is kept: the new text goes into the run that held the first
    replaced character, later covered characters are deleted from their runs.
    A zero-length span inserts. Tabs and breaks inside the span are removed.
    """
    items = text_items(paragraph)
    covered = [i for i in items if i.start < end and i.end > start] if end > start else []

    if not covered:
        # Pure insertion (or replacing nothing): find where to put the text.
        text_nodes = [i for i in items if i.kind == "t"]
        target = next((i for i in text_nodes if i.start <= start <= i.end and i.end > i.start), None)
        if target is None:
            before = [i for i in items if i.end <= start]
            run = _new_run_like(paragraph, before[-1].run if before else (items[0].run if items else None))
            node = OxmlElement("w:t")
            _set_text(node, new_text)
            run.append(node)
            if before:
                anchor = before[-1].run
                if anchor.getparent() is not None:
                    anchor.addnext(run)
                else:
                    paragraph.append(run)
            else:
                ppr = paragraph.find(PPR)
                if ppr is not None:
                    ppr.addnext(run)
                else:
                    paragraph.insert(0, run)
            return
        offset = start - target.start
        _set_text(target.element, target.element.text[:offset] + new_text + target.element.text[offset:])
        return

    inserted = False
    for item in covered:
        local_start = max(start, item.start) - item.start
        local_end = min(end, item.end) - item.start
        if item.kind == "t":
            text = item.element.text or ""
            if not inserted:
                _set_text(item.element, text[:local_start] + new_text + text[local_end:])
                inserted = True
            else:
                _set_text(item.element, text[:local_start] + text[local_end:])
        else:  # tab / br fully inside the span
            parent_run = item.run
            parent_run.remove(item.element)
    if not inserted:
        # Span held only tabs/breaks: put the text where the first one was.
        first = covered[0]
        run = _new_run_like(paragraph, first.run)
        node = OxmlElement("w:t")
        _set_text(node, new_text)
        run.append(node)
        anchor = first.run
        if anchor.getparent() is not None:
            anchor.addnext(run)
        else:
            paragraph.append(run)
    for item in covered:
        _drop_if_empty_run(item.run)


def set_paragraph_text(paragraph, text: str, keep_prefix: int = 0) -> None:
    """Replace everything after the first ``keep_prefix`` characters with ``text``."""
    length = len(paragraph_text(paragraph))
    replace_span(paragraph, keep_prefix, length, text)


# --------------------------------------------------------------------------
# Structure helpers
# --------------------------------------------------------------------------


def iter_container_children(container) -> Iterator[object]:
    """Paragraphs and tables directly in ``container`` (looking through content controls)."""
    for child in container:
        if child.tag in (P, TBL):
            yield child
        elif child.tag == SDT:
            content = child.find(SDT_CONTENT)
            if content is not None:
                yield from iter_container_children(content)


def iter_paragraphs(container) -> Iterator[object]:
    """Every paragraph below ``container`` in reading order, including inside tables."""
    for child in iter_container_children(container):
        if child.tag == P:
            yield child
        else:
            for row in child.findall(TR):
                for cell in row.findall(TC):
                    yield from iter_paragraphs(cell)


def ensure_cell_ends_with_paragraph(cell) -> None:
    """Word requires every table cell to end with a paragraph."""
    children = [c for c in cell if c.tag != qn("w:tcPr")]
    if not children or children[-1].tag != P:
        cell.append(OxmlElement("w:p"))


def is_blank(paragraph) -> bool:
    return not paragraph_text(paragraph).strip()


_WHITESPACE = re.compile(r"\s+")


def squash(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def clone(element):
    return deepcopy(element)


def ancestor(element, tag):
    node = element.getparent()
    while node is not None:
        if node.tag == tag:
            return node
        node = node.getparent()
    return None


def child_of(element, tag) -> Optional[object]:
    return element.find(tag)
