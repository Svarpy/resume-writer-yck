"""Template-faithful resume generation from an uploaded sample ``.docx``.

The sample is analysed at the OOXML level (``resume_core.ooxml.analysis``):
header, sections and one *exemplar* per kind of line (paragraph, bullet,
``Label: values`` line, company/role/date row, spacer). Generation deep-copies
the sample package and rebuilds only the text-bearing content: every exemplar is
cloned and just its text changes, so page setup, styles, numbering, tab stops,
borders, tables, headers/footers and run formatting come straight from the sample.
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from resume_core.ooxml.analysis import (
    BULLET_RE,
    LABEL_RE,
    Block,
    ContactItem,
    DocumentAnalysis,
    Line,
    Region,
    analyze_document,
    contact_items,
    DATE_RANGE,
    find_date,
)
from resume_core.ooxml.xmlutil import (
    P,
    TC,
    ensure_cell_ends_with_paragraph,
    iter_paragraphs,
    paragraph_text,
    replace_span,
    set_paragraph_text,
)
from resume_core.render.parse import (
    clean_lines,
    detect_known_company,
    fallback_role_date,
    looks_like_role_line,
    normalize_date_text,
    normalize_experience_bullet_text,
    phone_hyperlink,
    split_known_company_line,
    strip_bullet_marker,
)

if TYPE_CHECKING:
    from resume_core.render.models import ResumeContent, ResumeFormat


class TemplateGenerationError(Exception):
    """The sample document could not be used as a template."""


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def build_resume_from_template(content: "ResumeContent", fmt: "ResumeFormat", output_path: Path) -> Path:
    """Clone the stored sample ``.docx`` and rebuild its content from ``content``."""
    from docx import Document

    template_path = Path(fmt.template_path)
    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found: {template_path}")

    document = Document(str(template_path))
    analysis = analyze_document(document)
    if not analysis.regions and analysis.name is None:
        raise TemplateGenerationError(
            "The uploaded sample has no recognisable resume content (no name or section headings)."
        )
    _Generator(analysis, content, fmt).run()
    apply_core_properties(document, content)
    document.core_properties.last_modified_by = content.author.strip() or content.name.strip()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    return output_path


def drop_unused_hyperlink_rels(document) -> None:
    """Remove external hyperlink relationships nothing refers to any more (they would keep old addresses)."""
    roots = [document.element]
    for section in document.sections:
        for part in (section.header, section.footer, section.first_page_header, section.first_page_footer,
                     section.even_page_header, section.even_page_footer):
            if part is not None and not part.is_linked_to_previous:
                roots.append(part._element)
    used = {node.get(qn("r:id")) for root in roots for node in root.iter(qn("w:hyperlink")) if node.get(qn("r:id"))}
    for rel_id, rel in list(document.part.rels.items()):
        if rel.is_external and rel.reltype.endswith("/hyperlink") and rel_id not in used:
            document.part.rels.pop(rel_id)


def apply_core_properties(document, content: "ResumeContent") -> None:
    """DOCX metadata: author, subject, title and keywords (Settings > Metadata)."""
    from resume_core.render.parse import split_keywords

    core = document.core_properties
    core.author = content.author.strip() or content.name.strip()
    core.subject = content.subject
    core.keywords = ", ".join(split_keywords(content.keyword_source(), content.keyword_count))
    core.title = content.title_template.replace("{name}", content.name.strip()).strip() or "Resume"


# --------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------


class _Plan:
    """One section to write: user settings (key, kind, heading) + its text."""

    def __init__(self, key: str, kind: str, heading: str, show_heading: bool, text: str, label: str) -> None:
        self.key, self.kind, self.heading, self.show_heading, self.text, self.label = (
            key, kind, heading, show_heading, text, label)


class _Generator:
    def __init__(self, analysis: DocumentAnalysis, content: "ResumeContent", fmt: "ResumeFormat") -> None:
        self.a = analysis
        self.content = content
        self.fmt = fmt
        self._heading_elements: list = []
        self.sample_name = analysis.name.text.strip() if analysis.name else ""
        self.sample_contact = analysis.contact.text if analysis.contact else ""
        self.sample_tagline = analysis.tagline.text.strip() if analysis.tagline else ""

    # -- orchestration ----------------------------------------------------
    def run(self) -> None:
        self._scrub_headers_and_footers()
        self._fill_header()
        plans = self._plans()
        self._rebuild_regions(plans)
        for cell in self.a.document.element.body.iter(TC):
            ensure_cell_ends_with_paragraph(cell)
        self._apply_typography()
        drop_unused_hyperlink_rels(self.a.document)

    # -- Writer font / size choices: always what was selected, whatever the sample uses ------
    _SYMBOL_FONTS = {"symbol", "wingdings", "wingdings 2", "wingdings 3", "webdings"}

    def _apply_typography(self) -> None:
        """Give the name, headings and all other text exactly the font and sizes chosen in the Writer."""
        a, fmt = self.a, self.fmt
        font = (fmt.font_name or "").strip()
        sizes = {"name": fmt.name_size * 2, "heading": fmt.heading_size * 2, "body": fmt.body_size * 2}
        if not font and not any(sizes.values()):
            return
        name_el = a.name.paragraph if a.name is not None else None
        heading_ids = {id(el) for el in self._heading_elements}
        for paragraph in iter_paragraphs(a.document.element.body):
            if paragraph is name_el:
                group = "name"
            elif id(paragraph) in heading_ids:
                group = "heading"
            else:
                group = "body"
            targets = []
            for run in paragraph.iter(qn("w:r")):
                rpr = run.find(qn("w:rPr"))
                targets.append(rpr if rpr is not None else self._new_rpr(run))
            targets.append(self._paragraph_mark_rpr(paragraph))  # sets bullet glyph size and empty-line height
            for rpr in targets:
                self._style_rpr(rpr, font, sizes[group])

    @staticmethod
    def _new_rpr(run):
        rpr = OxmlElement("w:rPr")
        run.insert(0, rpr)
        return rpr

    @staticmethod
    def _paragraph_mark_rpr(paragraph):
        ppr = paragraph.find(qn("w:pPr"))
        if ppr is None:
            ppr = OxmlElement("w:pPr")
            paragraph.insert(0, ppr)
        rpr = ppr.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            anchor = next((c for c in ppr if c.tag in (qn("w:sectPr"), qn("w:pPrChange"))), None)
            if anchor is not None:
                anchor.addprevious(rpr)
            else:
                ppr.append(rpr)
        return rpr

    def _style_rpr(self, rpr, font: str, size_half_points: int) -> None:
        fonts = rpr.find(qn("w:rFonts"))
        current = (fonts.get(qn("w:ascii")) or "").casefold() if fonts is not None else ""
        if font and current not in self._SYMBOL_FONTS:  # keep bullet symbol fonts intact
            if fonts is None:
                fonts = OxmlElement("w:rFonts")
                _insert_in_schema_order(rpr, fonts)
            for attribute in list(fonts.attrib):
                del fonts.attrib[attribute]
            for attribute in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                fonts.set(qn(attribute), font)
        if size_half_points:
            for tag in ("w:sz", "w:szCs"):
                node = rpr.find(qn(tag))
                if node is None:
                    node = OxmlElement(tag)
                    _insert_in_schema_order(rpr, node)
                node.set(qn("w:val"), str(size_half_points))

    def _plans(self) -> list[_Plan]:
        content = self.content
        plans: list[_Plan] = []
        if content.section_plan:
            for spec in content.section_plan:
                if spec.kind == "education":
                    text = "\n\n".join(e for e in content.education_entries if e.strip())
                else:
                    text = content.text_for(spec.key)
                if not text.strip():
                    continue
                plans.append(_Plan(spec.key, spec.kind, spec.heading, getattr(spec, "show_heading", True),
                                   text, spec.label))
            return plans
        # Legacy content (no plan): sections in the sample's own order.
        for region in self.a.regions:
            if region.kind == "education":
                text = "\n\n".join(e for e in content.education_entries if e.strip())
            else:
                text = content.text_for(region.key)
            if text.strip():
                plans.append(_Plan(region.key, region.kind, "", True, text, region.heading_text))
        return plans

    # -- header -------------------------------------------------------------
    def _fill_header(self) -> None:
        a, c = self.a, self.content
        if a.name is not None:
            if c.name.strip():
                set_paragraph_text(a.name.paragraph, c.name.strip())
            else:
                self._remove_block(a.name)
        if a.tagline is not None:
            if getattr(c, "tagline", "").strip():
                set_paragraph_text(a.tagline.paragraph, c.tagline.strip())
            else:
                self._remove_block(a.tagline)
        if a.contact is not None:
            self._fill_contact_lines([a.contact, *a.contact_extra], c)

    def _remove_block(self, block) -> None:
        parent = block.element.getparent()
        if parent is not None:
            parent.remove(block.element)
            if parent.tag == TC:
                ensure_cell_ends_with_paragraph(parent)

    def _fill_contact_lines(self, blocks: list, c) -> None:
        """Fill one or more contact lines (``email | phone | city`` in one paragraph, or one item per line)."""
        wanted = {"email": c.email.strip(), "phone": c.phone.strip(), "other": c.location.strip()}
        used: set[str] = set()
        present = {item.kind for block in blocks for item in contact_items(paragraph_text(block.paragraph))}
        for block in blocks:
            self._fill_contact(block.paragraph, wanted, used)
            if not paragraph_text(block.paragraph).strip():
                self._remove_block(block)  # every item on this line was dropped
        missing = [(k, v) for k, v in wanted.items() if v and k not in present]
        if missing:
            primary = blocks[0].paragraph
            for _kind, value in missing:
                end = len(paragraph_text(primary))
                replace_span(primary, end, end, (self.a.contact_separator if end else "") + value)
            self._retarget_links(primary, wanted["email"], wanted["phone"])

    def _fill_contact(self, paragraph, wanted: dict, used: set) -> None:
        """Replace the items of one contact line with the user's values; items without a value are removed."""
        items = contact_items(paragraph_text(paragraph))
        plan: list[tuple[ContactItem, str]] = []
        for item in items:
            value = ""
            if item.kind in wanted and item.kind not in used:  # a repeat (second city, a LinkedIn link, ...) is dropped
                value = wanted[item.kind]
                used.add(item.kind)
            plan.append((item, value))
        for index in range(len(plan) - 1, -1, -1):  # right to left so earlier offsets stay valid
            item, value = plan[index]
            if value:
                replace_span(paragraph, item.val_start, item.val_end, value)
                continue
            # No value: drop the item together with one adjacent separator.
            if index > 0:
                start, end = plan[index - 1][0].seg_end, item.seg_end
            elif len(plan) > 1:
                start, end = item.seg_start, plan[1][0].seg_start
            else:
                start, end = item.seg_start, item.seg_end
            replace_span(paragraph, start, end, "")
        self._retarget_links(paragraph, wanted["email"], wanted["phone"])

    def _retarget_links(self, paragraph, email: str, phone: str) -> None:
        """Point the contact hyperlinks at the new email / phone (a link keeps the sample's address otherwise)."""
        for link in paragraph.iter(qn("w:hyperlink")):
            rel_id = link.get(qn("r:id"))
            if not rel_id:
                continue
            text = "".join(node.text or "" for node in link.iter(qn("w:t")))
            if "@" in text and email:
                url = f"mailto:{email}"
            elif phone and re.search(r"\d{5,}", re.sub(r"\D", "", text)):
                url = phone_hyperlink(phone)
            else:
                continue
            link.set(qn("r:id"), self.a.document.part.relate_to(
                url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                is_external=True,
            ))

    # -- headers / footers must not leak the sample's personal details -------
    def _scrub_headers_and_footers(self) -> None:
        """Replace the sample's name and contact details wherever headers/footers repeat them (any letter case)."""
        document, c = self.a.document, self.content
        replacements: list[tuple[str, str]] = []
        if self.sample_name:
            replacements.append((self.sample_name, c.name.strip()))
            core = re.split(r"[,(]", self.sample_name)[0].strip()  # "Jane Doe, MBA" also appears as "Jane Doe"
            if core and core != self.sample_name:
                replacements.append((core, c.name.strip()))
        values = {"email": c.email, "phone": c.phone, "other": c.location}
        blocks = [b for b in (self.a.contact, *self.a.contact_extra) if b is not None]
        for block in blocks:
            for item in contact_items(block.text):
                old = block.text[item.val_start:item.val_end].strip()
                if old:
                    replacements.append((old, values.get(item.kind, "").strip()))
        if not replacements:
            return
        replacements.sort(key=lambda pair: -len(pair[0]))  # longest first ("Jane Doe, MBA" before "Jane Doe")
        seen: set[int] = set()
        for section in document.sections:
            for part in (section.header, section.footer, section.first_page_header, section.first_page_footer,
                         section.even_page_header, section.even_page_footer):
                if part is None or part.is_linked_to_previous or id(part._element) in seen:
                    continue
                seen.add(id(part._element))
                for paragraph in iter_paragraphs(part._element):
                    for old, new in replacements:
                        pattern = re.compile(re.escape(old), re.IGNORECASE)
                        while True:
                            match = pattern.search(paragraph_text(paragraph))
                            if match is None:
                                break
                            replace_span(paragraph, match.start(), match.end(), new)

    # -- regions ----------------------------------------------------------------
    def _rebuild_regions(self, plans: list[_Plan]) -> None:
        a = self.a
        by_key = {r.key: r for r in a.regions}

        # Placeholders mark where each sample region sits before it is removed.
        anchors: dict[str, list] = {}
        for region in a.regions:
            blocks = region.all_blocks()
            if not blocks:
                continue
            markers = []
            seen_parents: set[int] = set()
            for block in blocks:
                parent = block.element.getparent()
                if id(parent) in seen_parents:
                    continue
                seen_parents.add(id(parent))
                marker = OxmlElement("w:p")
                block.element.addprevious(marker)
                markers.append((marker, parent))
            anchors[region.key] = markers

        for region in a.regions:
            for block in region.all_blocks():
                parent = block.element.getparent()
                if parent is not None:
                    parent.remove(block.element)

        if not plans:
            self._drop_markers(anchors)
            return

        linear = a.is_linear and bool(a.regions)
        first_emitted = True
        outputs: list[tuple[_Plan, list, Optional[Region]]] = []
        for plan in plans:
            region = by_key.get(plan.key)
            column_cells = self._column_cells(region) if region is not None else []
            elements = self._build_section(plan, region, first=first_emitted, columns=max(1, len(column_cells)))
            first_emitted = False
            outputs.append((plan, elements, region))

        if linear:
            # One container: write everything at the first region's position, in plan order.
            first_marker = anchors[a.regions[0].key][0][0]
            for _plan, elements, _region in outputs:
                for el in _flatten(elements):
                    first_marker.addprevious(el)
        else:
            last_marker = None
            for plan, elements, region in outputs:
                markers = anchors.get(plan.key) if region is not None else None
                if markers:
                    self._place_in_columns(elements, markers, self._column_cells(region))
                    last_marker = markers[-1][0]
                else:
                    # Section the sample does not have: after the last section written so far.
                    target = last_marker if last_marker is not None else (
                        anchors[a.regions[-1].key][-1][0] if a.regions else None)
                    if target is None:
                        continue
                    for el in _flatten(elements):
                        target.addprevious(el)
        self._drop_markers(anchors)

    def _drop_markers(self, anchors: dict[str, list]) -> None:
        for markers in anchors.values():
            for marker, _owner in markers:
                parent = marker.getparent()
                if parent is not None:
                    parent.remove(marker)
                    if parent.tag == TC:
                        ensure_cell_ends_with_paragraph(parent)

    def _column_cells(self, region: Region) -> list:
        """Sibling table cells the section's content was spread over (e.g. two columns of skills)."""
        cells: list = []
        for block in region.content:
            if block.kind in ("blank", "separator"):
                continue
            if block.container.tag == TC and block.container not in cells:
                cells.append(block.container)
        rows = [cell.getparent() for cell in cells]  # keep references: lxml proxies are not id-stable
        if len(cells) > 1 and all(row is rows[0] for row in rows):
            return cells
        return []

    def _place_in_columns(self, elements, markers: list, cells: list) -> None:
        heading_marker = markers[0][0]
        if isinstance(elements, tuple):
            heading_part, columns = elements
            for el in heading_part:
                heading_marker.addprevious(el)
            targets = [marker for cell in cells for marker, owner in markers if owner is cell]
            if len(targets) < len(columns):
                targets = [heading_marker] * len(columns)
            for chunk, marker in zip(columns, targets):
                for el in chunk:
                    marker.addprevious(el)
            return
        for el in elements:
            heading_marker.addprevious(el)

    # -- building one section -------------------------------------------------------
    def _build_section(self, plan: _Plan, region: Optional[Region], *, first: bool, columns: int):
        a = self.a
        head: list = []
        # separator before the heading (not before the first section written)
        if not first and a.uses_separators:
            sep_block = (region.lead_separators[0] if region is not None and region.lead_separators
                         else a.separator_block)
            if sep_block is not None:
                head.append(deepcopy(sep_block.element))
        heading_text = plan.heading or (region.heading_text if region is not None and region.has_heading else "")
        if plan.show_heading and (heading_text or region is None):
            if not heading_text:
                heading_text = plan.label.upper() if self._headings_uppercase() else plan.label
            template = region.heading if region is not None and region.heading is not None else a.heading_block
            if template is not None:
                heading_el = deepcopy(template.element)
                set_paragraph_text(heading_el if heading_el.tag == P else next(heading_el.iter(P)), heading_text)
                head.append(heading_el)
                self._heading_elements.append(heading_el if heading_el.tag == P else next(heading_el.iter(P)))
            else:
                plain = self._plain_heading(heading_text)
                head.append(plain)
                self._heading_elements.append(plain)
        if region is not None:
            head.extend(deepcopy(b.element) for b in _leading_blanks(region))
        lines = self._content_elements(plan, region)
        if columns > 1 and len(lines) > 1:
            size = -(-len(lines) // columns)
            chunks = [lines[i:i + size] for i in range(0, len(lines), size)]
            while len(chunks) < columns:
                chunks.append([])
            return head, chunks
        return head + lines

    def _headings_uppercase(self) -> bool:
        heads = [r.heading_text for r in self.a.regions if r.has_heading]
        return bool(heads) and sum(1 for h in heads if h.isupper()) * 2 >= len(heads)

    def _plain_heading(self, text: str):
        paragraph = OxmlElement("w:p")
        run = OxmlElement("w:r")
        rpr = OxmlElement("w:rPr")
        rpr.append(OxmlElement("w:b"))
        run.append(rpr)
        node = OxmlElement("w:t")
        node.text = text
        run.append(node)
        paragraph.append(run)
        return paragraph

    # exemplar lookup with document-wide fallback -----------------------------------
    def _ex(self, region: Optional[Region], *roles: str) -> Optional[Line]:
        for role in roles:
            if region is not None and role in region.exemplars:
                return region.exemplars[role]
        for role in roles:
            if role in self.a.exemplars:
                return self.a.exemplars[role]
        return None

    def _content_elements(self, plan: _Plan, region: Optional[Region]) -> list:
        kind = plan.kind
        raw = clean_lines(plan.text)
        out: list = []
        if kind == "education":
            return self._education(plan, region)
        if kind == "experience":
            return self._experience(raw, region)
        if kind == "skills":
            exemplar = self._ex(region, "skill")
            if exemplar is not None and exemplar.blocks[0].element.tag == qn("w:tbl"):
                return self._skills_table(exemplar, [strip_bullet_marker(l.strip()) for l in raw if l.strip()])
        for line in raw:
            stripped = line.strip()
            if not stripped:
                continue
            if kind == "skills":
                out.append(self._skill(self._ex(region, "skill", "bullet", "plain"), strip_bullet_marker(stripped)))
                continue
            bullet = re.match(r"^(?:[-*]|•)\s+(.*)$", stripped)
            if bullet and kind != "paragraph":
                out.append(self._bullet(self._ex(region, "bullet", "skill_bullet", "plain"), bullet.group(1).strip()))
            elif kind == "bullets" and _split_dated(stripped):
                left, right = _split_dated(stripped)
                out.append(self._unit(self._ex(region, "company", "unit", "plain"), left, right))
            else:
                out.append(self._plain(self._ex(region, "plain", "bullet"), stripped))
        return [el for el in out if el is not None]

    # -- line builders -------------------------------------------------------------------
    def _clone_line(self, line: Line) -> list:
        return [deepcopy(b.element) for b in line.blocks]

    def _plain(self, line: Optional[Line], text: str):
        if line is None:
            return self._plain_heading_free(text)
        element = self._clone_line(line)[0]
        paragraph = element if element.tag == P else next(element.iter(P))
        prefix = _marker_length(paragraph_text(paragraph)) if line.role == "bullet" else 0
        replace_span(paragraph, prefix, len(paragraph_text(paragraph)), text)
        return element

    def _plain_heading_free(self, text: str):
        paragraph = OxmlElement("w:p")
        run = OxmlElement("w:r")
        node = OxmlElement("w:t")
        node.text = text
        run.append(node)
        paragraph.append(run)
        return paragraph

    def _bullet(self, line: Optional[Line], text: str):
        text = normalize_experience_bullet_text(text)
        if line is None:
            return self._plain_heading_free("• " + text)
        element = self._clone_line(line)[0]
        paragraph = element if element.tag == P else next(element.iter(P))
        old = paragraph_text(paragraph)
        replace_span(paragraph, _marker_length(old), len(old), text)
        return element

    def _skill(self, line: Optional[Line], text: str):
        if line is None:
            return self._plain_heading_free(text)
        element = self._clone_line(line)[0]
        paragraph = element if element.tag == P else next(element.iter(P))
        old = paragraph_text(paragraph)
        prefix = _marker_length(old)
        match = LABEL_RE.match(old[prefix:])
        label, _, value = text.partition(":") if ":" in text else ("", "", text)
        if not match:
            replace_span(paragraph, prefix, len(old), text)
            return element
        label_end = prefix + len(match.group(1))
        gap_end = label_end + len(match.group(2))
        # value first (right side), then the label, so offsets stay valid
        replace_span(paragraph, gap_end, len(old), value.strip() if label else value.strip())
        if label:
            replace_span(paragraph, prefix, label_end, label.strip() + ":")
        else:
            replace_span(paragraph, prefix, gap_end, "")
        return element

    def _skills_table(self, line: Line, texts: list[str]) -> list:
        """Skills laid out as a table (label | values): one row per skill line, row formatting from the sample."""
        table = deepcopy(line.blocks[0].element)
        rows = table.findall(qn("w:tr"))
        prototype = rows[0]
        label_cell = prototype.findall(qn("w:tc"))[0]
        colon = paragraph_text(label_cell.find(qn("w:p"))).rstrip().endswith(":")
        for row in rows:
            table.remove(row)
        for text in texts:
            label, _sep, values = text.partition(":") if ":" in text else ("", "", text)
            row = deepcopy(prototype)
            cells = row.findall(qn("w:tc"))
            for cell, value in ((cells[0], (label.strip() + (":" if colon and label.strip() else ""))), (cells[1], values.strip())):
                paragraphs = cell.findall(qn("w:p"))
                set_paragraph_text(paragraphs[0], value)
                for extra in paragraphs[1:]:
                    cell.remove(extra)
            table.append(row)
        return [table] if texts else []

    def _unit(self, line: Optional[Line], left: str, date: str):
        """A company / role / education row: ``left`` text and a date. Returns one element or a list."""
        date = normalize_date_text(date) if date.strip() else ""
        if line is None:
            return self._plain_heading_free(f"{left}\t{date}" if date else left)
        elements = self._clone_line(line)
        date_para = None
        left_para = None
        for element in elements:
            for paragraph in ([element] if element.tag == P else list(element.iter(P))):
                text = paragraph_text(paragraph)
                span = find_date(text)
                if span and date_para is None:
                    date_para = (paragraph, span, text)
                elif text.strip() and left_para is None:
                    left_para = (paragraph, text)
        if date_para is not None:
            paragraph, (ds, de), text = date_para
            before, after = text[:ds], text[de:]
            wrapped = before.rstrip().endswith(("(", "[")) and after.strip()[:1] in (")", "]")
            # Keep the sample's punctuation around the date: "(date)" brackets and the separator
            # ("," or "|") between the left text and the date stay exactly as in the sample.
            stripped = before.rstrip(" \t|,;–—-([").rstrip()
            left_end = len(stripped)
            same_paragraph_left = bool(stripped) and not (left_para and left_para[0] is paragraph)
            date_first = not stripped and after.strip() and left_para is None
            if date_first:
                # "March 2021 – Present <tab> Company, Role": the left text follows the date.
                start = de + len(after) - len(after.lstrip(" \t|,;–—-"))
                self._set_left(paragraph, start, len(text), left)
                replace_span(paragraph, ds, de, date)
                return elements if len(elements) > 1 else elements[0]
            replace_span(paragraph, ds, de if wrapped else len(text), date)
            if same_paragraph_left:
                self._set_left(paragraph, 0, left_end, left)
            elif left_para is not None and left_para[0] is not paragraph:
                self._set_left(left_para[0], 0, len(left_para[1]), left)
        elif left_para is not None:
            self._set_left(left_para[0], 0, len(left_para[1]), left)
        return elements if len(elements) > 1 else elements[0]

    def _set_left(self, paragraph, start: int, end: int, left: str) -> None:
        """Fill the left text, honouring the sample's ``segment | segment`` formatting.

        When the sample's left text has several separated segments (for example a bold
        company name, a separator and a normal-weight location) the user's ``A | B`` parts
        are written into the matching segments so each keeps its own run formatting.
        """
        text = paragraph_text(paragraph)
        parts = re.split(r"(\s*[|·]\s*)", text[start:end])
        segments, separators = parts[0::2], parts[1::2]
        user_parts = [p.strip() for p in re.split(r"\s*\|\s*", left) if p.strip()] or [left.strip()]
        if len(segments) < 2:
            replace_span(paragraph, start, end, left.strip())
            return
        merged = user_parts[: len(segments)]
        if len(user_parts) > len(segments):
            merged[-1] = ", ".join([merged[-1], *user_parts[len(segments):]])
        offsets = []
        position = start
        for index, segment in enumerate(segments):
            offsets.append((position, position + len(segment)))
            position += len(segment) + (len(separators[index]) if index < len(separators) else 0)
        for index in range(len(segments) - 1, -1, -1):
            seg_start, seg_end = offsets[index]
            if index < len(merged):
                replace_span(paragraph, seg_start, seg_end, merged[index])
            else:  # fewer parts than segments: drop the segment and the separator before it
                replace_span(paragraph, offsets[index - 1][1], seg_end, "")

    # -- experience / education ---------------------------------------------------------
    def _job_exemplars(self, region: Optional[Region]) -> tuple[Optional[Line], Optional[Line]]:
        """Exemplars for a company row and a role row of the experience section.

        A sample often keeps the company row and its first role row in ONE table (and later roles in
        single-row tables). Such a table is split by row so that each row is filled from its own line.
        """
        company = self._ex(region, "company", "unit")
        if company is None:
            return None, None
        rows = self._dated_rows(company)
        if len(rows) > 1:
            company = rows[0]
        role = region.exemplars.get("role") if region is not None else None
        if role is not None and len(self._dated_rows(role)) > 1:
            role = self._dated_rows(role)[-1]
        if role is None and len(rows) > 1:
            role = rows[-1]
        if role is None and region is not None:
            first = region.exemplars.get("company") or region.exemplars.get("unit")
            for line in region.lines:  # a later single-line unit worded like a job title
                if line.role == "unit" and line is not first and looks_like_role_line(re.sub(
                        r"\s+", " ", (find_date(line.text) and line.text[: find_date(line.text)[0]]) or line.text)):
                    row_lines = self._dated_rows(line)
                    role = row_lines[-1] if len(row_lines) > 1 else line
                    break
        return company, role or company

    @staticmethod
    def _dated_rows(line: Line) -> list[Line]:
        """One Line per row when ``line`` is a table whose every row holds a date, else ``[line]``."""
        block = line.blocks[0]
        if len(line.blocks) != 1 or block.element.tag != qn("w:tbl"):
            return [line]
        rows = block.element.findall(qn("w:tr"))
        if len(rows) < 2 or not all(find_date(" ".join(paragraph_text(p) for p in row.iter(P))) for row in rows):
            return [line]
        out: list[Line] = []
        for keep in range(len(rows)):
            table = deepcopy(block.element)
            for position, row in enumerate(table.findall(qn("w:tr"))):
                if position != keep:
                    table.remove(row)
            paragraphs = list(table.iter(P))
            out.append(Line("unit", [Block(element=table, paragraphs=paragraphs, container=block.container,
                                           text="\n".join(paragraph_text(p) for p in paragraphs), kind="dated")]))
        return out

    def _experience(self, raw: list[str], region: Optional[Region]) -> list:
        companies = self.content.known_companies
        out: list = []
        current_company: Optional[int] = None
        role_index: dict[Optional[int], int] = {}
        previous_was_bullet = False
        company_ex, role_ex = self._job_exemplars(region)
        gap_ex = region.exemplars.get("gap") if region is not None else None
        emitted_unit = False

        def emit_unit(left: str, date: str, is_role: bool) -> None:
            nonlocal previous_was_bullet, emitted_unit
            if emitted_unit and previous_was_bullet and gap_ex is not None:
                out.extend(self._clone_line(gap_ex))
            built = self._unit(role_ex if is_role else company_ex, left, date)
            out.extend(built if isinstance(built, list) else [built])
            previous_was_bullet = False
            emitted_unit = True

        for line in raw:
            stripped = line.strip()
            if not stripped:
                continue
            clean = strip_bullet_marker(stripped)
            dated = _split_dated(clean)
            if dated:
                left, right = dated
                detected = detect_known_company(left, companies)
                if detected is not None:
                    current_company = detected
                    role_index.setdefault(current_company, 0)
                    emit_unit(left, right, False)
                else:
                    is_role = looks_like_role_line(left)
                    if is_role and fallback_role_date(current_company, role_index.get(current_company, 0), companies) is not None:
                        role_index[current_company] = role_index.get(current_company, 0) + 1
                    emit_unit(left, right, is_role)
                continue
            known = split_known_company_line(clean, companies)
            if known:
                left, right, current_company = known
                role_index.setdefault(current_company, 0)
                emit_unit(left, right, False)
                continue
            if looks_like_role_line(clean):
                index = role_index.get(current_company, 0)
                role_date = fallback_role_date(current_company, index, companies)
                if role_date:
                    role_index[current_company] = index + 1
                    emit_unit(clean, role_date, True)
                    continue
                if clean == stripped and emitted_unit and not previous_was_bullet:
                    emit_unit(clean, "", True)  # a role written without dates, right under its company
                    continue
            out.append(self._bullet(self._ex(region, "bullet", "plain"), clean))
            previous_was_bullet = True
        return [el for el in out if el is not None]

    def _education(self, plan: _Plan, region: Optional[Region]) -> list:
        out: list = []
        unit_ex = self._ex(region, "unit", "company", "role")
        plain_ex = self._ex(region, "plain", "bullet")
        for entry in re.split(r"\n\s*\n", plan.text.strip()):
            for line in clean_lines(entry):
                stripped = line.strip()
                if not stripped:
                    continue
                dated = _split_dated(stripped)
                if dated:
                    built = self._unit(unit_ex, dated[0], dated[1])
                    out.extend(built if isinstance(built, list) else [built])
                else:
                    out.append(self._plain(plain_ex, stripped))
        return [el for el in out if el is not None]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _split_dated(line: str) -> Optional[tuple[str, str]]:
    """``(left text, date)`` of a line such as ``Acme | Remote   Jan 2020 - Present``, or None.

    The left text is kept exactly as typed (inner ``|`` separators included). The date has to close
    the line (an annotation such as ``| GPA 4.0`` may follow), so a sentence that merely mentions a
    range ("... across 2023-2024, recognised for ...") is never mistaken for a dated heading.
    """
    text = line.strip()
    if "\t" in text:
        left, right = text.rsplit("\t", 1)
        span = find_date(right)
        if span and left.strip():
            return left.strip().rstrip(" |,-–—"), right[span[0]:span[1]]
    for match in reversed(list(DATE_RANGE.finditer(text))):
        left = text[: match.start()].strip()
        rest = text[match.end():].strip()
        if not left:
            continue
        if rest and not (rest[0] in "|(" and len(rest.split()) <= 6):
            continue
        if len(left.split()) > 16 or left.endswith("."):
            continue
        return left.rstrip(" |,-–—"), match.group()
    return None


_RPR_ORDER = (
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline", "shadow",
    "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
    "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs",
    "em", "lang", "eastAsianLayout", "specVanish", "oMath",
)


def _insert_in_schema_order(rpr, element) -> None:
    """Insert ``element`` into ``w:rPr`` where the OOXML schema wants it (Word is strict about order)."""
    ranks = {qn(f"w:{name}"): index for index, name in enumerate(_RPR_ORDER)}
    rank = ranks.get(element.tag, len(_RPR_ORDER))
    for child in rpr:
        if ranks.get(child.tag, len(_RPR_ORDER)) > rank:
            child.addprevious(element)
            return
    rpr.append(element)


def _marker_length(text: str) -> int:
    """Length of a literal bullet marker (glyph + spacing/tab) at the start of ``text``."""
    match = BULLET_RE.match(text)
    return len(match.group(1)) if match else 0


def _leading_blanks(region: Region) -> list:
    blanks = []
    for block in region.content:
        if block.kind in ("blank",):
            blanks.append(block)
        else:
            break
    return blanks


def _flatten(elements) -> list:
    if isinstance(elements, tuple):
        head, columns = elements
        return list(head) + [el for chunk in columns for el in chunk]
    return list(elements)
