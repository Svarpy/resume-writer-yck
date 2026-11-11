"""OOXML analysis of a sample resume.

``analyze_document`` reads a sample ``.docx`` at the XML level and works out:

* the header (name, optional tagline, contact line),
* the sections (heading, optional leading separator, content lines),
* for every kind of line (paragraph, bullet, ``Label: values`` skill line,
  company/role/date row, plain line, spacer) an *exemplar* — the actual XML
  elements of the sample — and the character spans inside it that hold text.

Nothing about the look of the sample is re-derived or approximated: the
generator (``generate.py``) clones these exemplars and only swaps their text.
That is what makes the output match the sample for any content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from docx.oxml.ns import qn

from resume_core.ooxml.styles import RunFormat, StyleSheet
from resume_core.ooxml.xmlutil import (
    P,
    TBL,
    iter_paragraphs,
    paragraph_text,
    squash,
)

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary", "professional summary", "profile", "professional profile", "objective", "career objective",
        "about", "about me", "executive summary", "career summary", "personal statement",
    ),
    "skills": (
        "skills", "technical skills", "core competencies", "core skills", "key skills", "skills & tools",
        "skills and tools", "technical proficiencies", "areas of expertise", "expertise",
    ),
    "experience": (
        "experience", "work experience", "professional experience", "employment", "work history",
        "employment history", "career history", "relevant experience", "experience summary",
    ),
    "education": ("education", "academic background", "academics", "education & training", "qualifications",
                  "education and training"),
    "certifications": ("certifications", "certificates", "licenses", "licences", "certifications & licenses",
                       "licenses & certifications", "training & certifications"),
    "projects": ("projects", "personal projects", "selected projects", "key projects", "academic projects"),
    "awards": ("awards", "honors", "honours", "awards & honors", "achievements", "accomplishments"),
    "publications": ("publications", "papers", "research"),
    "languages": ("languages",),
    "interests": ("interests", "hobbies", "interests & hobbies"),
    "volunteering": ("volunteering", "volunteer experience", "community involvement", "leadership"),
}
_ALIAS_TO_KEY = {alias: key for key, aliases in SECTION_ALIASES.items() for alias in aliases}
_KIND_BY_KEY = {
    "summary": "paragraph", "skills": "skills", "experience": "experience", "education": "education",
    "certifications": "bullets", "projects": "bullets", "awards": "bullets", "publications": "bullets",
    "languages": "bullets", "interests": "bullets", "volunteering": "bullets",
}

_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
          r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_POINT = rf"(?:{_MONTH}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_END = rf"(?:{_POINT}|Present|Current|Now|Ongoing|Till\s+Date|To\s+Date)"
DATE_RANGE = re.compile(rf"\b{_POINT}\s*(?:-|–|—|to)\s*{_END}\b", re.IGNORECASE)
DATE_SINGLE = re.compile(rf"^\s*(?:{_MONTH}\s+\d{{4}}|\d{{4}})\s*$", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{6,}\d")
BULLET_RE = re.compile(r"^(\s*[•▸●○▪◦■□➢➤‣⁃*\-–]\s*(?:\t\s*)?)\S")
LABEL_RE = re.compile(r"^(\s*[^:\n]{1,45}?:)(\s+)\S")
SEPARATOR_SPLIT = re.compile(r"(\s*[|·•]\s*|\s{3,}|\t|\n)")
URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin|github|gitlab|behance|medium|twitter|x)\.com/\S*|\b[\w-]+\.(?:io|dev|me|tech|co|org|net)(?:/\S*)?", re.IGNORECASE)
LOCATION_RE = re.compile(r"^[^\W\d_][\w .'’-]*,\s*[^\W\d_][\w .'’-]*$")


_NUMBERING_PREFIX = re.compile(r"^\s*(?:\d{1,2}|[ivxlc]{1,4}|[a-z])[.)]\s+", re.IGNORECASE)


def heading_core(heading: str) -> str:
    """Heading text without numbering ("2. ", "IV) ") and a trailing colon, for matching."""
    return _NUMBERING_PREFIX.sub("", squash(heading)).strip(" :").casefold()


def canonical_key(heading: str) -> Optional[str]:
    return _ALIAS_TO_KEY.get(heading_core(heading))


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = "section_" + slug if slug else "section"
    return slug[:32]


def find_date(text: str) -> Optional[tuple[int, int]]:
    match = DATE_RANGE.search(text)
    if match:
        return match.start(), match.end()
    if DATE_SINGLE.match(text):
        stripped = text.strip()
        start = text.index(stripped)
        return start, start + len(stripped)
    return None


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass
class Block:
    """A paragraph, or a "content table" (a table without headings, e.g. a company/date row)."""

    element: object
    paragraphs: list
    container: object
    text: str = ""
    kind: str = "plain"      # blank | separator | bullet | skill | dated | plain
    lead_date: bool = False  # the date is at the very start (company line is on the previous block)
    labeled: bool = False    # bullet or line of the form "Label: values"

    @property
    def paragraph(self):
        return self.paragraphs[0]


@dataclass
class Line:
    """One logical line of a section: a single block or a (left text + date) pair of blocks."""

    role: str                # blank | bullet | skill | unit | plain
    blocks: list[Block]
    labeled: bool = False

    @property
    def elements(self) -> list:
        return [b.element for b in self.blocks]

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


@dataclass
class Region:
    key: str
    heading_text: str
    has_heading: bool
    kind: str
    heading: Optional[Block] = None
    lead_separators: list[Block] = field(default_factory=list)
    content: list[Block] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    exemplars: dict[str, Line] = field(default_factory=dict)

    def all_blocks(self) -> list[Block]:
        blocks = list(self.lead_separators)
        if self.heading is not None:
            blocks.append(self.heading)
        blocks.extend(self.content)
        return blocks


@dataclass
class HeadingSignature:
    style_id: str
    fmt: RunFormat
    bordered: bool


@dataclass
class DocumentAnalysis:
    document: object
    sheet: StyleSheet
    name: Optional[Block]
    tagline: Optional[Block]
    contact: Optional[Block]
    regions: list[Region]
    heading_signature: Optional[HeadingSignature]
    exemplars: dict[str, Line]           # document-wide fallback exemplars by role
    uses_separators: bool
    separator_block: Optional[Block]
    heading_block: Optional[Block]
    contact_separator: str
    # numbers for the saved format
    font_name: str
    name_size: int
    heading_size: int
    body_size: int
    contact_extra: list[Block] = field(default_factory=list)  # further contact lines (stacked headers)
    body_half_pts: int = 22      # exact dominant body size in half-points (body_size is this, rounded)
    warnings: list[str] = field(default_factory=list)

    def region_for(self, key: str) -> Optional[Region]:
        return next((r for r in self.regions if r.key == key), None)

    @property
    def is_linear(self) -> bool:
        """True when every region sits directly in one container (so regions can be reordered)."""
        containers = {id(b.container) for r in self.regions for b in r.all_blocks()}
        return len(containers) <= 1

    def section_summary(self) -> list[dict]:
        """Section list in the shape of ``sections.items`` settings rows."""
        rows = []
        for region in self.regions:
            rows.append({
                "key": region.key,
                "label": (region.heading_text.title() if region.heading_text.isupper() else region.heading_text)
                if region.has_heading else region.key.replace("_", " ").title(),
                "heading": region.heading_text if region.has_heading else "",
                "kind": region.kind,
                "width": "full" if region.kind in ("experience", "paragraph") else "half",
                "enabled": True,
                "show_heading": region.has_heading,
                "min_words": 0,
                "max_words": 0,
            })
        return rows


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------


class _Para:
    __slots__ = ("el", "text", "container", "fmt", "style_id", "bordered", "numbered", "bold_all")

    def __init__(self, el, sheet: StyleSheet) -> None:
        self.el = el
        self.text = paragraph_text(el)
        self.container = el.getparent()
        self.fmt = sheet.dominant_format(el)
        self.style_id = sheet.paragraph_style_id(el)
        self.bordered = sheet.has_bottom_border(el)
        self.numbered = sheet.has_numbering(el)
        self.bold_all = sheet.all_bold(el)


def _is_bullet(text: str, numbered: bool) -> bool:
    return numbered or bool(BULLET_RE.match(text))


def analyze_document(document) -> DocumentAnalysis:
    sheet = StyleSheet(document)
    body = document.element.body
    paras = [_Para(el, sheet) for el in iter_paragraphs(body)]
    nonblank = [p for p in paras if p.text.strip()]
    warnings: list[str] = []

    body_half_pts = _body_half_points(paras)
    body_size = round(body_half_pts / 2 + 0.01)  # 9.5 pt shows as 10, never banker's-rounded down

    # --- name / contact -------------------------------------------------
    contact_para = next(
        (p for p in nonblank if (EMAIL_RE.search(p.text) or PHONE_RE.search(p.text))
         and len(p.text) < 220 and not _is_alias_heading(p.text)), None)
    name_para = None
    for p in nonblank:
        if p is contact_para:
            break
        if _is_alias_heading(p.text):
            break
        name_para = p
        break
    if name_para is None and nonblank:
        name_para = nonblank[0] if nonblank[0] is not contact_para else None

    # --- headings ---------------------------------------------------------
    heading_paras, signature = _detect_headings(paras, nonblank, sheet, body_size, name_para, contact_para)

    # --- tagline: short non-heading line between name and the first heading/contact ----
    tagline_para = None
    if name_para is not None:
        after_name = False
        for p in nonblank:
            if p is name_para:
                after_name = True
                continue
            if not after_name:
                continue
            if p in heading_paras or p is contact_para:
                break
            if len(p.text.split()) <= 12 and p.fmt.size_half_pts <= max(name_para.fmt.size_half_pts, 1):
                tagline_para = p
            break

    # --- further contact lines right after the first one (name / email / phone / city on separate lines) ----
    extra_contact: list[_Para] = []
    if contact_para is not None:
        following = nonblank[nonblank.index(contact_para) + 1:]
        for p in following:
            if p in heading_paras or not _contactish(p.text):
                break
            extra_contact.append(p)

    # --- blocks (paragraphs, plus content tables as single blocks) ---------------
    special = {id(p.el) for p in heading_paras}
    for p in (name_para, contact_para, tagline_para, *extra_contact):
        if p is not None:
            special.add(id(p.el))
    blocks = _build_blocks(body, paras, special, sheet)

    by_el = {id(b.element): b for b in blocks}
    name_block = by_el.get(id(name_para.el)) if name_para else None
    contact_block = by_el.get(id(contact_para.el)) if contact_para else None
    tagline_block = by_el.get(id(tagline_para.el)) if tagline_para else None
    extra_blocks = [by_el[id(p.el)] for p in extra_contact if id(p.el) in by_el]
    heading_ids = {id(p.el) for p in heading_paras}

    # --- regions ----------------------------------------------------------------
    regions: list[Region] = []
    pre_blocks: list[Block] = []
    current: Optional[Region] = None
    header_ids = {id(b.element) for b in (name_block, contact_block, tagline_block, *extra_blocks) if b is not None}
    for block in blocks:
        if id(block.element) in header_ids:
            continue
        if id(block.element) in heading_ids:
            current = Region(key="", heading_text=squash(block.text), has_heading=True, kind="paragraph", heading=block)
            regions.append(current)
            continue
        (current.content if current is not None else pre_blocks).append(block)

    if any(b.kind not in ("blank", "separator") for b in pre_blocks):
        regions.insert(0, Region(key="", heading_text="", has_heading=False, kind="paragraph", content=pre_blocks))
    elif pre_blocks:
        pass  # spacing between the contact line and the first heading: left untouched

    # separators that precede a heading belong to that heading
    for index, region in enumerate(regions):
        if index == 0:
            continue
        while region_prev_tail_is_separator(regions[index - 1]):
            region.lead_separators.insert(0, regions[index - 1].content.pop())
    # a leading separator before the very first heading
    if regions and regions[0].has_heading:
        while pre_blocks and pre_blocks[-1].kind == "separator":
            regions[0].lead_separators.insert(0, pre_blocks.pop())

    used_keys: set[str] = set()
    for region in regions:
        _classify_region(region, sheet)
        key = canonical_key(region.heading_text) if region.has_heading else None
        if key is None:
            key = "summary" if not region.has_heading else slugify(region.heading_text)
        base, n = key, 2
        while key in used_keys:
            key = f"{base}_{n}"
            n += 1
        used_keys.add(key)
        region.key = key
        region.kind = _infer_kind(region)
        _pick_exemplars(region)

    doc_exemplars: dict[str, Line] = {}
    for region in regions:
        for role, line in region.exemplars.items():
            doc_exemplars.setdefault(role, line)

    separators = [r.lead_separators[0] for r in regions if r.lead_separators]
    uses_separators = len(separators) >= max(1, (len(regions) - 1) // 2)
    separator_block = separators[0] if separators else None
    heading_block = next((r.heading for r in regions if r.heading is not None), None)

    contact_separator = _contact_separator(contact_block)
    font_name = _font_name(document, sheet, paras)
    name_size = round(name_para.fmt.size_half_pts / 2) if name_para and name_para.fmt.size_half_pts else 16
    heading_size = (round(signature.fmt.size_half_pts / 2) if signature and signature.fmt.size_half_pts
                    else max(body_size, 12))
    if not regions:
        warnings.append("No section headings were recognised; the sample may not look like a resume.")
    return DocumentAnalysis(
        document=document, sheet=sheet, name=name_block, tagline=tagline_block, contact=contact_block,
        contact_extra=extra_blocks,
        regions=regions, heading_signature=signature, exemplars=doc_exemplars,
        uses_separators=uses_separators, separator_block=separator_block, heading_block=heading_block,
        contact_separator=contact_separator, font_name=font_name, name_size=name_size,
        heading_size=heading_size, body_size=body_size, body_half_pts=body_half_pts, warnings=warnings,
    )


def _contactish(text: str) -> bool:
    """A short line that is only contact data: email, phone, link or a 'City, State' location."""
    stripped = text.strip()
    if not stripped or len(stripped.split()) > 10 or stripped.endswith("."):
        return False
    if EMAIL_RE.search(stripped) or URL_RE.search(stripped):
        return True
    digits = re.sub(r"\D", "", stripped)
    if PHONE_RE.search(stripped) and len(digits) >= 7 and len(re.sub(r"[\d\s()+.\-]", "", stripped)) <= 6:
        return True
    return len(stripped.split()) <= 5 and bool(LOCATION_RE.match(re.sub(r"^[^\w]+", "", stripped)))


def region_prev_tail_is_separator(region: Region) -> bool:
    return bool(region.content) and region.content[-1].kind == "separator"


def _is_alias_heading(text: str) -> bool:
    return heading_core(text) in _ALIAS_TO_KEY


def _body_half_points(paras: list[_Para]) -> int:
    counts: dict[int, int] = {}
    for p in paras:
        size = p.fmt.size_half_pts
        if size and len(p.text.strip()) > 25:
            counts[size] = counts.get(size, 0) + len(p.text)
    return max(counts, key=counts.get) if counts else 22


def _font_name(document, sheet: StyleSheet, paras: list[_Para]) -> str:
    counts: dict[str, int] = {}
    for p in paras:
        if p.fmt.font and p.text.strip():
            counts[p.fmt.font] = counts.get(p.fmt.font, 0) + len(p.text)
    if counts:
        return max(counts, key=counts.get)
    try:
        font = document.styles["Normal"].font.name
        if font:
            return font
    except Exception:  # noqa: BLE001
        pass
    return "Arial"


def _detect_headings(paras, nonblank, sheet, body_size, name_para, contact_para):
    candidates = [
        p for p in nonblank
        if p is not name_para and p is not contact_para and len(p.text.split()) <= 6
        and _is_alias_heading(p.text) and not EMAIL_RE.search(p.text)
    ]
    signature: Optional[HeadingSignature] = None
    if candidates:
        # The signature shared by most alias headings is "what a heading looks like" here.
        sigs = [(p.style_id, p.fmt, p.bordered) for p in candidates]
        best = max(set(sigs), key=sigs.count)
        signature = HeadingSignature(*best)
        headings = [
            p for p in nonblank
            if p is not name_para and p is not contact_para
            and (p in candidates or (
                (p.style_id, p.fmt, p.bordered) == best and len(p.text.split()) <= 5
                and not p.text.rstrip().endswith((".", ","))
                and not find_date(p.text) and not EMAIL_RE.search(p.text)
                and not _is_bullet(p.text, p.numbered)
            ))
        ]
        return headings, signature

    # No recognisable headings: fall back to visual cues (style / caps+bold / border).
    visual = [
        p for p in nonblank
        if p is not name_para and p is not contact_para and len(p.text.split()) <= 5
        and not find_date(p.text) and not _is_bullet(p.text, p.numbered)
        and (sheet.style_name(p.style_id).casefold().startswith("heading")
             or (p.bold_all and (p.text.isupper() or p.bordered or p.fmt.size_half_pts > body_size * 2)))
    ]
    if visual:
        first = visual[0]
        signature = HeadingSignature(first.style_id, first.fmt, first.bordered)
        visual = [p for p in visual if (p.style_id, p.fmt, p.bordered) == (first.style_id, first.fmt, first.bordered)]
    return visual, signature


def _build_blocks(body, paras: list[_Para], special: set[int], sheet: StyleSheet) -> list[Block]:
    """Paragraph/table blocks in reading order, with ``kind`` classification."""
    special_els = {id(p.el): p for p in paras if id(p.el) in special}

    def has_special(table) -> bool:
        return any(id(p) in special_els for p in table.iter(P))

    anchors: dict[int, object] = {}
    for table in body.iter(TBL):
        if has_special(table):
            continue
        # outermost table without headings/name/contact
        ancestor_tbl = table.getparent()
        outermost = table
        while ancestor_tbl is not None:
            if ancestor_tbl.tag == TBL and not has_special(ancestor_tbl):
                outermost = ancestor_tbl
            ancestor_tbl = ancestor_tbl.getparent()
        for p in table.iter(P):
            anchors[id(p)] = outermost

    blocks: list[Block] = []
    last_anchor = None
    for para in paras:
        anchor = anchors.get(id(para.el))
        if anchor is not None:
            if anchor is last_anchor:
                blocks[-1].paragraphs.append(para.el)
                continue
            blocks.append(Block(element=anchor, paragraphs=[para.el], container=anchor.getparent()))
            last_anchor = anchor
        else:
            blocks.append(Block(element=para.el, paragraphs=[para.el], container=para.container))
            last_anchor = None
    for block in blocks:
        _classify_block(block, sheet)
    return blocks


def _classify_block(block: Block, sheet: StyleSheet) -> None:
    texts = [paragraph_text(p) for p in block.paragraphs]
    block.text = "\n".join(t for t in texts if t.strip()) if len(texts) > 1 else texts[0]
    if not block.text.strip():
        block.kind = "separator" if len(block.paragraphs) == 1 and sheet.has_bottom_border(block.paragraph) else "blank"
        return
    first = block.paragraph
    if block.element.tag == qn("w:tbl") and _is_label_value_table(block.element):
        block.kind, block.labeled = "skill", True
        return
    if len(block.paragraphs) == 1:
        numbered = sheet.has_numbering(first)
        if _is_bullet(block.text, numbered):
            block.kind = "bullet"
            body = block.text.lstrip()
            match = BULLET_RE.match(block.text)
            if match:
                body = block.text[match.end(1):]
            block.labeled = bool(LABEL_RE.match(body))
            return
    for text in texts:
        date = find_date(text)
        if date:
            block.kind = "dated"
            before, after = text[: date[0]], text[date[1]:]
            # "lead date": the date starts the line and the company/role is on the previous line. Trailing text
            # only counts as an annotation ("| GPA 4.0"); real text after the date means a date-first line.
            block.lead_date = (len(block.paragraphs) == 1 and not before.strip()
                               and (not after.strip() or after.lstrip(" \t")[:1] in ("|", ",", ";", "(")))
            return
    if len(block.paragraphs) == 1 and LABEL_RE.match(block.text) and sheet.first_run_bold(first):
        block.kind = "skill"
        block.labeled = True
        return
    block.kind = "plain"


def _is_label_value_table(table) -> bool:
    """A table of ``label | values`` rows (skills laid out in two columns) without any dates."""
    rows = table.findall(qn("w:tr"))
    if not rows:
        return False
    for row in rows:
        cells = row.findall(qn("w:tc"))
        if len(cells) != 2:
            return False
        texts = ["".join(paragraph_text(p) for p in cell.findall(qn("w:p"))).strip() for cell in cells]
        if not all(texts) or len(texts[0].split()) > 6 or find_date(texts[1]):
            return False
    return True


def _classify_region(region: Region, sheet: StyleSheet) -> None:
    """Group content blocks into logical lines (pairing a company line with a date-only line)."""
    lines: list[Line] = []
    for block in region.content:
        if block.kind in ("blank", "separator"):
            lines.append(Line("blank", [block]))
        elif block.kind == "bullet":
            lines.append(Line("bullet", [block], labeled=block.labeled))
        elif block.kind == "skill":
            lines.append(Line("skill", [block], labeled=True))
        elif block.kind == "dated":
            previous = lines[-1] if lines else None
            if (block.lead_date and previous is not None and previous.role == "plain"
                    and previous.blocks[-1].container is block.container):
                previous.role = "unit"
                previous.blocks.append(block)
            else:
                lines.append(Line("unit", [block]))
        else:
            lines.append(Line("plain", [block]))
    region.lines = lines


_EDUCATION_WORDS = re.compile(
    r"\b(?:universit\w*|college|institute|school|academy|bachelor\w*|master\w*|b\.?\s?tech|m\.?\s?tech|b\.?\s?e\b|"
    r"b\.?\s?sc|m\.?\s?sc|b\.?\s?com|m\.?\s?com|b\.?\s?a\b|m\.?\s?a\b|mba|bca|mca|diploma|ph\.?\s?d|"
    r"cgpa|gpa|percentage|higher secondary|hsc|ssc|class (?:x|xii)|degree)\b", re.IGNORECASE)


def _infer_kind(region: Region) -> str:
    key_kind = _KIND_BY_KEY.get(region.key)
    roles = [line.role for line in region.lines]
    units = roles.count("unit")
    bullets = roles.count("bullet")
    skills = sum(1 for line in region.lines if line.role == "skill" or (line.role == "bullet" and line.labeled))
    if key_kind in ("skills", "education", "experience", "paragraph") and region.key == "summary":
        return "paragraph"
    if key_kind == "education":
        return "education"
    if key_kind == "skills" or (skills and skills >= max(1, len(roles)) * 0.5 and not units):
        return "skills"
    if key_kind == "experience" or (units and bullets):
        return "experience"
    if key_kind:
        return key_kind
    body = " ".join(line.text for line in region.lines)
    if units and not bullets and _EDUCATION_WORDS.search(body):
        return "education"  # dated lines naming degrees / institutions, whatever the heading says
    if units:
        return "experience"
    if bullets:
        return "bullets"
    return "paragraph"


def _pick_exemplars(region: Region) -> None:
    ex: dict[str, Line] = {}
    previous_unit_adjacent = False
    for index, line in enumerate(region.lines):
        role = line.role
        if role == "bullet":
            ex.setdefault("skill_bullet" if line.labeled else "bullet", line)
            if line.labeled:
                ex.setdefault("skill", line)
            else:
                ex.setdefault("bullet", line)
        elif role == "skill":
            ex.setdefault("skill", line)
        elif role == "plain":
            ex.setdefault("plain", line)
        elif role == "unit":
            ex.setdefault("unit", line)
            if "company" not in ex:
                ex["company"] = line
            elif "role" not in ex and previous_unit_adjacent:
                ex["role"] = line
            previous_unit_adjacent = True
            continue
        elif role == "blank":
            # A spacer that sits between content lines and is followed by a unit = role gap.
            nxt = region.lines[index + 1] if index + 1 < len(region.lines) else None
            if index > 0 and nxt is not None and nxt.role == "unit":
                ex.setdefault("gap", line)
        previous_unit_adjacent = False
    region.exemplars = ex


# --------------------------------------------------------------------------
# Contact line
# --------------------------------------------------------------------------


@dataclass
class ContactItem:
    kind: str       # email | phone | other
    seg_start: int
    seg_end: int
    val_start: int
    val_end: int


def contact_items(text: str) -> list[ContactItem]:
    items: list[ContactItem] = []
    position = 0
    for part in SEPARATOR_SPLIT.split(text):
        start, end = position, position + len(part)
        position = end
        if not part.strip() or SEPARATOR_SPLIT.fullmatch(part):
            continue
        email = EMAIL_RE.search(part)
        phone = PHONE_RE.search(part)
        link = URL_RE.search(part)
        if email:
            items.append(ContactItem("email", start, end, start + email.start(), start + email.end()))
        elif phone and len(re.sub(r"\D", "", phone.group())) >= 7:
            items.append(ContactItem("phone", start, end, start + phone.start(), start + phone.end()))
        elif link:
            items.append(ContactItem("link", start, end, start + link.start(), start + link.end()))
        else:
            stripped = part.lstrip()
            offset = len(part) - len(stripped)
            # skip leading emoji / symbols (anything that is not a letter or digit)
            while stripped and not stripped[0].isalnum():
                stripped = stripped[1:]
                offset += 1
            items.append(ContactItem("other", start, end, start + offset, start + len(part.rstrip())))
    return items


def _contact_separator(block: Optional[Block]) -> str:
    if block is None:
        return "  |  "
    text = block.text
    items = contact_items(text)
    if len(items) >= 2:
        between = text[items[0].seg_end:items[1].seg_start]
        if between:
            return between
    return "  |  "
