"""Finding and checking the ``{{...}}`` placeholders of a template document.

A template is an ordinary Word document in which person-specific text has been replaced by

* **fields**  ``{{name}}``                      - replaced by a value,
* **blocks**  ``{{#jobs}} ... {{/jobs}}``       - the paragraphs / table rows in between repeat once per item.

This module makes the markers easy to work with (every marker alone in its own run, tables split at the
rows where a block starts or ends), pairs the markers and reports mistakes. It never guesses what a line
"means": the template says so.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Iterator, Optional

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from resume_core.ooxml.xmlutil import P, R, RPR, T, TBL, TC, TR, paragraph_text, text_items

TOKEN_RE = re.compile(r"\{\{\s*([#/]?)\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_WHOLE_RUN = re.compile(r"\s*\{\{\s*([#/]?)\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}\s*")

ROOT_FIELDS = ("name", "tagline", "email", "phone", "location")
BLOCK_FIELDS = ("text", "label", "values", "company", "location", "title", "dates", "degree", "major",
                "institution", "grade")
INNER_BLOCKS = ("items", "jobs", "roles", "bullets", "degrees")


@dataclass
class Token:
    kind: str                 # field | start | end
    name: str
    run: object               # the w:r holding only this marker
    paragraph: object
    index: int = 0            # position among all tokens of the document


@dataclass
class Block:
    name: str
    start: Token
    end: Token
    parent: Optional["Block"] = None
    children: list["Block"] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)   # fields directly inside (not in a child block)

    @property
    def depth(self) -> int:
        return 0 if self.parent is None else self.parent.depth + 1


# --------------------------------------------------------------------------
# Making every marker live alone in its own run
# --------------------------------------------------------------------------


def _new_run_after(run, children) -> object:
    clone = OxmlElement("w:r")
    props = run.find(RPR)
    if props is not None:
        clone.append(deepcopy(props))
    for child in children:
        clone.append(child)
    run.addnext(clone)
    return clone


def _split_text_item(item, offset: int) -> None:
    """Split a ``w:t`` item into two runs at ``offset`` characters."""
    run, node = item.run, item.element
    text = node.text or ""
    following = []
    sibling = node.getnext()
    while sibling is not None:
        following.append(sibling)
        sibling = sibling.getnext()
    tail = OxmlElement("w:t")
    tail.text = text[offset:]
    tail.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    node.text = text[:offset]
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for child in following:
        run.remove(child)
    _new_run_after(run, [tail, *following])


def _split_boundary(paragraph, offset: int) -> None:
    for item in text_items(paragraph):
        if item.kind == "t" and item.start < offset < item.end:
            _split_text_item(item, offset - item.start)
            return


def _lone(run, node) -> None:
    """Make ``node`` the only content of its run (split off whatever shares the run)."""
    content = [c for c in run if c.tag != RPR]
    position = content.index(node)
    after = content[position + 1:]
    for child in after:
        run.remove(child)
    if after:
        _new_run_after(run, after)
    if content[:position]:
        run.remove(node)
        _new_run_after(run, [node])  # the original run keeps what came before the marker


def isolate_tokens(paragraph) -> None:
    """Give every ``{{...}}`` its own run (even when Word split it over runs or typed text around it)."""
    for _ in range(200):
        text = paragraph_text(paragraph)
        for match in TOKEN_RE.finditer(text):
            start, end = match.span()
            items = [i for i in text_items(paragraph) if i.start < end and i.end > start]
            if (len(items) == 1 and items[0].kind == "t" and items[0].start == start and items[0].end == end
                    and sum(1 for c in items[0].run if c.tag != RPR) == 1):
                continue
            _split_boundary(paragraph, start)
            _split_boundary(paragraph, end)
            items = [i for i in text_items(paragraph) if i.start >= start and i.end <= end and i.end > i.start]
            texts = [i for i in items if i.kind == "t"]
            if not texts:
                continue
            first = texts[0]
            first.element.text = match.group(0)
            first.element.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            for other in texts[1:]:
                run = other.run
                run.remove(other.element)
                if all(c.tag == RPR for c in run) and run.getparent() is not None:
                    run.getparent().remove(run)
            _lone(first.run, first.element)
            break
        else:
            return


def token_of_run(run) -> Optional[tuple[str, str]]:
    """``(kind, name)`` when this run holds only a marker, else None."""
    content = [c for c in run if c.tag != RPR]
    if len(content) != 1 or content[0].tag != T:
        return None
    match = _WHOLE_RUN.fullmatch(content[0].text or "")
    if not match:
        return None
    return {"#": "start", "/": "end", "": "field"}[match.group(1)], match.group(2)


def paragraph_tokens(paragraph) -> list[Token]:
    out = []
    for run in paragraph.iter(R):
        found = token_of_run(run)
        if found:
            out.append(Token(found[0], found[1], run, paragraph))
    return out


def all_tokens(root) -> list[Token]:
    tokens: list[Token] = []
    for paragraph in root.iter(P):
        tokens.extend(paragraph_tokens(paragraph))
    for index, token in enumerate(tokens):
        token.index = index
    return tokens


def normalize(root) -> None:
    """Isolate every marker, then split tables where a block starts or ends between rows."""
    for paragraph in list(root.iter(P)):
        if "{{" in paragraph_text(paragraph):
            isolate_tokens(paragraph)
    for _ in range(50):
        if not _split_one_table(root):
            break


# --------------------------------------------------------------------------
# Pairing
# --------------------------------------------------------------------------


def pair_blocks(tokens: list[Token], errors: Optional[list[str]] = None) -> list[Block]:
    """Match ``{{#x}}`` with ``{{/x}}`` (properly nested). Mistakes are appended to ``errors``."""
    errors = errors if errors is not None else []
    blocks: list[Block] = []
    stack: list[Block] = []
    for token in tokens:
        if token.kind == "start":
            block = Block(token.name, token, token, parent=stack[-1] if stack else None)
            if stack:
                stack[-1].children.append(block)
            stack.append(block)
            blocks.append(block)
        elif token.kind == "end":
            if not stack:
                errors.append(f"{{{{/{token.name}}}}} has no matching {{{{#{token.name}}}}}")
            elif stack[-1].name != token.name:
                errors.append(f"{{{{#{stack[-1].name}}}}} is closed by {{{{/{token.name}}}}}; blocks must nest")
                stack.pop()
            else:
                stack.pop().end = token
        elif stack:
            stack[-1].fields.append(token.name)
    for block in stack:
        errors.append(f"{{{{#{block.name}}}}} is never closed with {{{{/{block.name}}}}}")
    return [b for b in blocks if b.end is not b.start]


# --------------------------------------------------------------------------
# Containers, rows and table splitting
# --------------------------------------------------------------------------

_CONTAINERS = (qn("w:body"), TC)


def _enclosing_container(node):
    node = node.getparent()
    while node is not None and node.tag not in _CONTAINERS:
        node = node.getparent()
    return node


def _child_of(container, node):
    """The ancestor-or-self of ``node`` that is a direct child of ``container``."""
    while node is not None and node.getparent() is not container:
        node = node.getparent()
    return node


def _chain(node) -> list:
    out = []
    while node is not None:
        out.append(node)
        node = node.getparent()
    return out


def common_container(a, b):
    """Lowest body / table cell that contains both nodes."""
    seen = {id(x) for x in _chain(a)}
    node = b
    while node is not None:
        if id(node) in seen and node.tag in _CONTAINERS:
            return node
        node = node.getparent()
    return None


def _row_of(element, node):
    """The row of table ``element`` that contains ``node``."""
    while node is not None and node.getparent() is not element:
        node = node.getparent()
    return node if node is not None and node.tag == TR else None


def _split_table(table, first_moved_row) -> None:
    rows = table.findall(TR)
    position = rows.index(first_moved_row)
    if position == 0:
        return
    clone = OxmlElement("w:tbl")
    for tag in ("w:tblPr", "w:tblGrid"):
        part = table.find(qn(tag))
        if part is not None:
            clone.append(deepcopy(part))
    for row in rows[position:]:
        table.remove(row)
        clone.append(row)
    table.addnext(clone)


def _split_one_table(root) -> bool:
    tokens = all_tokens(root)
    for block in pair_blocks(tokens):
        container = common_container(block.start.paragraph, block.end.paragraph)
        if container is None:
            continue
        start_el = _child_of(container, block.start.paragraph)
        end_el = _child_of(container, block.end.paragraph)
        if start_el is not None and start_el.tag == TBL:
            row = _row_of(start_el, block.start.paragraph)
            if row is not None and start_el.findall(TR).index(row) > 0 and not (
                    start_el is end_el and _same_cell(block)):
                _split_table(start_el, row)
                return True
        if end_el is not None and end_el.tag == TBL:
            row = _row_of(end_el, block.end.paragraph)
            rows = end_el.findall(TR)
            if row is not None and rows.index(row) < len(rows) - 1 and not (
                    start_el is end_el and _same_cell(block)):
                _split_table(end_el, rows[rows.index(row) + 1])
                return True
    return False


def _same_cell(block: Block) -> bool:
    a = _enclosing_container(block.start.paragraph)
    return a is not None and a is _enclosing_container(block.end.paragraph)


def block_range(block: Block):
    """``(container, first_element, last_element)`` of the siblings a block repeats."""
    container = common_container(block.start.paragraph, block.end.paragraph)
    return container, _child_of(container, block.start.paragraph), _child_of(container, block.end.paragraph)


def siblings(first, last) -> Iterator[object]:
    node = first
    while node is not None:
        yield node
        if node is last:
            return
        node = node.getnext()
