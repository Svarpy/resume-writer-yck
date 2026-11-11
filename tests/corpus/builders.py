"""A corpus of professionally styled text-only resumes (fresher and experienced), built with python-docx.

Each ``Spec`` picks one option per dimension a real resume template varies in: header layout, heading style,
bullet style, how dates are placed, how skills are laid out, fonts/margins and the section list. The
corpus covers the combinations common in Word templates, Google Docs exports and hand-made resumes.
Everything a sample says is made of unique tokens (``zq...``) so tests can prove none of it leaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

NAME = "Zqmarcus Quillfeather"
EMAIL = "zqmarcus.quillfeather@zqmail.example"
PHONE = "+91 98765 43210"
CITY = "Zqville, Zqstate"
LINKEDIN = "linkedin.com/in/zqmarcus"


@dataclass
class Spec:
    id: str
    level: str                      # fresher | experienced
    header: str = "centered"        # centered | left | table | title | stacked
    icons: bool = False             # emoji / symbols in the contact line
    heading: str = "border_caps"    # border_caps | heading1 | shaded | colored | plain_bold | underline | sep_paragraph | caps_plain | heading2
    bullet: str = "list_style"      # list_style | glyph | dash | arrow | square
    dates: str = "tab"              # tab | table | nextline | paren | pipe | comma
    skills: str = "labels"          # labels | bullets | comma | table | dash
    font: str = "Calibri"
    size: float = 11
    margin: float = 0.8
    sections: list[tuple[str, str]] = field(default_factory=list)  # (heading text, kind)
    date_style: str = "month"       # month | numeric | year | short
    hyperlinks: bool = False        # email as a real hyperlink
    layout: str = "flow"            # flow | two_col (sidebar table) | rows (each section in a table row)
    footer: bool = False            # header + footer carrying the name / email
    name_style: str = "plain"       # plain | credentials | allcaps
    numbered: bool = False          # List Number instead of bullets
    mixed_bullets: bool = False     # List Bullet for some bullets, literal glyph for others
    heading_row: bool = False       # heading is a shaded table row
    fragment: bool = False          # every text run is split word by word (spell-check / revision splits)
    sdt: bool = False               # name and headings wrapped in Word content controls
    colon: bool = False             # headings end with ":" or are numbered ("1. Experience")
    nbsp: bool = False              # non-breaking spaces and double spaces in text


# ----- sample content (unique tokens so leaks are detectable) --------------------------------------------
def _dates(style: str, n: int) -> str:
    table = {
        "month": ["March 2021 – Present", "June 2018 – February 2021", "July 2016 – May 2018", "August 2014 – June 2016"],
        "numeric": ["03/2021 – Present", "06/2018 – 02/2021", "07/2016 – 05/2018", "08/2014 – 06/2016"],
        "year": ["2021 – Present", "2018 – 2021", "2016 – 2018", "2014 – 2016"],
        "short": ["Mar 2021 – Present", "Jun 2018 – Feb 2021", "Jul 2016 – May 2018", "Aug 2014 – Jun 2016"],
    }
    return table[style][n % 4]


def company(n: int) -> str:
    return ["Zqphyrion Labs", "Zqnova Systems", "Zqorbit Analytics", "Zqharbor Softworks"][n % 4]


ROLES = ["Senior Software Engineer", "Software Engineer", "Associate Engineer", "Software Intern"]
JOB_BULLETS = [
    "Designed zqservice pipelines processing zq120 events per second with zero downtime.",
    "Reduced zqlatency by 35% by rewriting the zqcache layer and adding zqmetrics dashboards.",
    "Led a zqteam of five engineers and mentored zqjunior developers through code reviews.",
    "Automated zqdeployments with containers, cutting release time from hours to minutes.",
]


def sample_texts(spec: Spec) -> dict[str, str]:
    return {"summary": "Results-driven zqengineer with experience building scalable zqplatforms and reliable zqservices for customers across industries.",
            "objective": "Motivated zqgraduate seeking an entry-level role to apply strong zqfundamentals and learn from experienced teams."}


# ----- low-level helpers --------------------------------------------------------------------------------------
def _font(run, spec: Spec, size: Optional[float] = None, bold=None, italic=None, color: Optional[str] = None,
          caps=False, small_caps=False, underline=None) -> None:
    run.font.name = spec.font
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), spec.font)
    run.font.size = Pt(size or spec.size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    run.font.all_caps = caps or None
    run.font.small_caps = small_caps or None
    if underline:
        run.underline = True


def _border(paragraph, side="bottom", size=6, color="808080", space=1) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    borders = ppr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        ppr.append(borders)
    el = OxmlElement(f"w:{side}")
    for k, v in (("val", "single"), ("sz", str(size)), ("space", str(space)), ("color", color)):
        el.set(qn(f"w:{k}"), v)
    borders.append(el)


def _shade(paragraph, fill: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def _fmt(paragraph, before=0, after=2, align=None, line=1.0) -> None:
    pf = paragraph.paragraph_format
    pf.space_before, pf.space_after, pf.line_spacing = Pt(before), Pt(after), line
    if align is not None:
        paragraph.alignment = align


def _no_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tbl_pr.append(borders)


def _text_width(spec: Spec) -> float:
    return 8.5 - 2 * spec.margin


class Builder:
    def __init__(self, spec: Spec) -> None:
        self.spec = spec
        self.doc = Document()
        section = self.doc.sections[0]
        section.left_margin = section.right_margin = Inches(spec.margin)
        section.top_margin = section.bottom_margin = Inches(max(0.5, spec.margin - 0.2))
        normal = self.doc.styles["Normal"]
        normal.font.name = spec.font
        normal.font.size = Pt(spec.size)
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), spec.font)
        self.first_section = True
        self.counter = 0
        self.container = self.doc
        self._unused_cells: set[int] = set()

    # -- container aware creation (document body or a table cell) -----------------------------------------
    def add_p(self, style=None):
        if self.container is not self.doc and id(self.container._tc) in self._unused_cells:
            self._unused_cells.discard(id(self.container._tc))
            paragraph = self.container.paragraphs[0]
            if style:
                paragraph.style = style
            return paragraph
        return self.container.add_paragraph(style=style) if style else self.container.add_paragraph()

    def add_t(self, rows, cols):
        if self.container is self.doc:
            return self.doc.add_table(rows=rows, cols=cols)
        return self.container.add_table(rows=rows, cols=cols)

    def use_cell(self, cell) -> None:
        self.container = cell
        self._unused_cells.add(id(cell._tc))

    def shown_name(self) -> str:
        return {"credentials": NAME + ", MBA", "allcaps": NAME.upper()}.get(self.spec.name_style, NAME)

    # -- header ---------------------------------------------------------------------------------------------
    def header(self) -> None:
        s = self.spec
        icons = ("✉ ", "☎ ", "⌂ ") if s.icons else ("", "", "")
        contact = [f"{icons[0]}{EMAIL}", f"{icons[1]}{PHONE}", f"{icons[2]}{CITY}"]
        sep = "  |  " if s.id.endswith(("1", "3", "5", "7", "9")) else "  •  "
        if s.header == "table":
            table = self.add_t(rows=1, cols=2)
            _no_borders(table)
            left, right = table.rows[0].cells
            p = left.paragraphs[0]
            _font(p.add_run(self.shown_name()), s, size=s.size + 9, bold=True)
            right_p = right.paragraphs[0]
            right_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            for i, text in enumerate(contact):
                if i:
                    right_p.add_run().add_break()
                _font(right_p.add_run(text), s)
            return
        if s.header == "stacked":
            p = self.add_p()
            _fmt(p, after=0, align=WD_ALIGN_PARAGRAPH.CENTER)
            _font(p.add_run(self.shown_name().upper()), s, size=s.size + 8, bold=True, color="1F3864")
            for text in contact:
                q = self.add_p()
                _fmt(q, after=0, align=WD_ALIGN_PARAGRAPH.CENTER)
                _font(q.add_run(text), s)
            return
        align = WD_ALIGN_PARAGRAPH.CENTER if s.header == "centered" else WD_ALIGN_PARAGRAPH.LEFT
        p = self.add_p(style="Title") if s.header == "title" else self.add_p()
        _fmt(p, after=2, align=align)
        _font(p.add_run(self.shown_name()), s, size=s.size + 9, bold=True)
        q = self.add_p()
        _fmt(q, after=4, align=align)
        parts = contact + ([LINKEDIN] if s.id.endswith(("2", "6")) else [])
        for i, text in enumerate(parts):
            if i:
                _font(q.add_run(sep), s)
            if s.hyperlinks and i == 0:
                self._hyperlink(q, text, f"mailto:{text.strip('✉ ')}")
            else:
                _font(q.add_run(text), s)

    def _hyperlink(self, paragraph, text: str, url: str) -> None:
        rel = paragraph.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
        link = OxmlElement("w:hyperlink")
        link.set(qn("r:id"), rel)
        run = OxmlElement("w:r")
        rpr = OxmlElement("w:rPr")
        color = OxmlElement("w:color")
        color.set(qn("w:val"), "0563C1")
        rpr.append(color)
        under = OxmlElement("w:u")
        under.set(qn("w:val"), "single")
        rpr.append(under)
        run.append(rpr)
        node = OxmlElement("w:t")
        node.text = text
        run.append(node)
        link.append(run)
        paragraph._p.append(link)

    # -- section headings ----------------------------------------------------------------------------------
    def heading(self, text: str) -> None:
        s = self.spec
        if s.colon:
            self.counter_heading = getattr(self, "counter_heading", 0) + 1
            text = f"{self.counter_heading}. {text}" if s.id.endswith(("1", "5")) else f"{text}:"
        if s.heading == "sep_paragraph" and not self.first_section:
            sep = self.add_p()
            _fmt(sep, after=2)
            _border(sep)
        self.first_section = False
        if s.heading_row:
            table = self.add_t(1, 1)
            _no_borders(table)
            cell = table.rows[0].cells[0]
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "D9E2F3")
            cell._tc.get_or_add_tcPr().append(shd)
            _font(cell.paragraphs[0].add_run(text.upper()), s, size=s.size + 1, bold=True, color="1F3864")
            return
        if s.heading == "heading1" or s.heading == "heading2":
            p = self.add_p(style="Heading 1" if s.heading == "heading1" else "Heading 2")
            _fmt(p, before=8, after=3)
            _font(p.add_run(text), s, size=s.size + 2, bold=True, color="1F3864")
            return
        p = self.add_p()
        _fmt(p, before=8, after=3)
        if s.heading == "border_caps":
            _font(p.add_run(text.upper()), s, size=s.size + 1, bold=True)
            _border(p)
        elif s.heading == "shaded":
            _shade(p, "1F3864")
            _font(p.add_run(" " + text.upper()), s, size=s.size + 1, bold=True, color="FFFFFF")
        elif s.heading == "colored":
            _font(p.add_run(text), s, size=s.size + 2, bold=True, color="2E74B5", small_caps=True)
            _border(p, color="2E74B5", size=8)
        elif s.heading == "underline":
            _font(p.add_run(text), s, size=s.size + 1, bold=True, underline=True)
        elif s.heading == "caps_plain":
            _font(p.add_run(text.upper()), s, size=s.size + 1, bold=True)
        else:  # plain_bold / sep_paragraph
            _font(p.add_run(text.upper() if s.heading == "sep_paragraph" else text), s, size=s.size + 1, bold=True)

    # -- body lines ---------------------------------------------------------------------------------------
    def bullet(self, text: str) -> None:
        s = self.spec
        self.counter += 1
        if s.numbered:
            p = self.add_p(style="List Number")
            _fmt(p, after=1)
            _font(p.add_run(text), s)
            return
        if s.mixed_bullets and self.counter % 2 == 0:
            p = self.add_p()
            _fmt(p, after=1)
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.first_line_indent = Inches(-0.2)
            _font(p.add_run(f"•\t{text}"), s)
            return
        if s.bullet == "numpr":  # list numbering applied directly to Normal paragraphs (Google Docs / LibreOffice style)
            p = self.add_p()
            _fmt(p, after=1)
            style_ppr = self.doc.styles["List Bullet"].element.pPr
            num_pr = OxmlElement("w:numPr")
            for tag, value in (("w:ilvl", "0"), ("w:numId", style_ppr.numPr.numId.val)):
                node = OxmlElement(tag)
                node.set(qn("w:val"), str(value))
                num_pr.append(node)
            p._p.get_or_add_pPr().append(num_pr)
            _font(p.add_run(text), s)
            return
        if s.bullet == "list_style":
            p = self.add_p(style="List Bullet")
            _fmt(p, after=1)
            _font(p.add_run(text), s)
            return
        glyph = {"glyph": "•", "arrow": "➢", "square": "▪", "dash": "-"}[s.bullet]
        p = self.add_p()
        _fmt(p, after=1)
        p.paragraph_format.left_indent = Inches(0.25)
        p.paragraph_format.first_line_indent = Inches(-0.2)
        if s.bullet == "dash":
            _font(p.add_run(f"- {text}"), s)
        else:
            _font(p.add_run(f"{glyph}\t{text}"), s)

    def plain(self, text: str, bold=False, italic=False, after=2, align=None) -> None:
        p = self.add_p()
        _fmt(p, after=after, align=align)
        _font(p.add_run(text), self.spec, bold=bold, italic=italic)

    def dated(self, left_bold: str, left_rest: str, date: str, sub: Optional[str] = None) -> None:
        """Company / role / education line with its date, laid out as ``spec.dates`` says."""
        s = self.spec
        if s.dates == "left":
            p = self.add_p()
            _fmt(p, before=4, after=1)
            p.paragraph_format.tab_stops.add_tab_stop(Inches(1.6), WD_TAB_ALIGNMENT.LEFT)
            _font(p.add_run(f"{date}\t"), s, italic=True)
            _font(p.add_run(left_bold), s, bold=True)
            if left_rest:
                _font(p.add_run(left_rest), s)
        elif s.dates == "tab":
            p = self.add_p()
            _fmt(p, before=4, after=1)
            p.paragraph_format.tab_stops.add_tab_stop(Inches(_text_width(s)), WD_TAB_ALIGNMENT.RIGHT)
            _font(p.add_run(left_bold), s, bold=True)
            if left_rest:
                _font(p.add_run(left_rest), s)
            _font(p.add_run(f"\t{date}"), s, italic=True)
        elif s.dates == "table":
            table = self.add_t(rows=1, cols=2)
            _no_borders(table)
            cells = table.rows[0].cells
            cells[0].width, cells[1].width = Inches(_text_width(s) - 1.9), Inches(1.9)
            lp = cells[0].paragraphs[0]
            _fmt(lp, before=4, after=1)
            _font(lp.add_run(left_bold), s, bold=True)
            if left_rest:
                _font(lp.add_run(left_rest), s)
            rp = cells[1].paragraphs[0]
            _fmt(rp, before=4, after=1, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _font(rp.add_run(date), s, italic=True)
        elif s.dates == "nextline":
            p = self.add_p()
            _fmt(p, before=4, after=0)
            _font(p.add_run(left_bold), s, bold=True)
            if left_rest:
                _font(p.add_run(left_rest), s)
            q = self.add_p()
            _fmt(q, after=1)
            _font(q.add_run(date), s, italic=True)
        elif s.dates == "paren":
            p = self.add_p()
            _fmt(p, before=4, after=1)
            _font(p.add_run(left_bold), s, bold=True)
            _font(p.add_run((left_rest or "") + f" ({date})"), s)
        elif s.dates == "pipe":
            p = self.add_p()
            _fmt(p, before=4, after=1)
            _font(p.add_run(left_bold), s, bold=True)
            _font(p.add_run((left_rest or "") + f" | {date}"), s)
        else:  # comma
            p = self.add_p()
            _fmt(p, before=4, after=1)
            _font(p.add_run(left_bold), s, bold=True)
            _font(p.add_run((left_rest or "") + f", {date}"), s)
        if sub:
            self.plain(sub, italic=True, after=1)

    def skills_block(self, rows: list[tuple[str, str]]) -> None:
        s = self.spec
        if s.skills == "table":
            table = self.add_t(rows=len(rows), cols=2)
            _no_borders(table)
            for row, (label, values) in zip(table.rows, rows):
                _font(row.cells[0].paragraphs[0].add_run(label), s, bold=True)
                _font(row.cells[1].paragraphs[0].add_run(values), s)
        elif s.skills == "comma":
            self.plain(", ".join(v for _l, v in rows), after=2)
        elif s.skills == "bullets":
            for label, values in rows:
                p = self.add_p(style="List Bullet")
                _fmt(p, after=1)
                _font(p.add_run(f"{label}: "), s, bold=True)
                _font(p.add_run(values), s)
        else:
            for label, values in rows:
                p = self.add_p()
                _fmt(p, after=1)
                _font(p.add_run(f"{label}{' –' if s.skills == 'dash' else ':'} "), s, bold=True)
                _font(p.add_run(values), s)

    # -- sections ---------------------------------------------------------------------------------------------
    def section(self, title: str, kind: str) -> None:
        s = self.spec
        self.heading(title)
        n = 0
        if kind == "paragraph":
            self.plain(sample_texts(s)["summary"], after=3, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        elif kind == "skills":
            self.skills_block([("Zqlanguages", "Python, Java, SQL, zqscript"), ("Zqframeworks", "React, Spring Boot, zqkit"),
                               ("Zqtools", "Git, Docker, Jenkins, zqcloud"), ("Zqdatabases", "MySQL, MongoDB, zqstore")])
        elif kind == "experience":
            jobs = 4 if s.level == "experienced" else 1
            for n in range(jobs):
                self.dated(company(n), f", {CITY.split(',')[0]}", _dates(s.date_style, n), sub=ROLES[n] if n % 2 == 0 else None)
                if n % 2:
                    self.plain(ROLES[n], italic=True, after=1)
                for text in JOB_BULLETS[: 3 if n % 2 == 0 else 2]:
                    self.bullet(text)
        elif kind == "education":
            self.dated("Bachelor of Technology in Zqscience", ", Zquniversity of Technology", _dates(s.date_style, 2),
                       sub="CGPA: 8.7 / 10")
            if s.level == "experienced":
                self.dated("Higher Secondary, Zqcollege", "", _dates(s.date_style, 3))
        elif kind == "projects":
            for i in range(2):
                self.plain(f"Zqproject {i + 1} – Zqdashboard built with React and Node (zqtech: Python, zqapi)", bold=True, after=1)
                self.bullet("Built a zqmodule that serves zq500 users and stores results securely.")
                self.bullet("Implemented zqtests achieving 90% coverage across zqcomponents.")
        elif kind == "bullets":
            for text in ("Winner of the zqhackathon among 200 teams.", "Published a zqpaper on distributed zqsystems.",
                         "Completed Zqcloud Certified Practitioner certification."):
                self.bullet(text)
        elif kind == "inline":
            self.plain("English (fluent), Hindi (native), Zqlanguage (basic)")
        elif kind == "references":
            self.plain("Available on request.", after=2)
        elif kind == "declaration":
            self.plain("I hereby declare that the above zqdetails are true to the best of my knowledge.", after=2)

    def build(self, path: Path) -> Path:
        spec = self.spec
        if spec.footer:
            section = self.doc.sections[0]
            _font(section.footer.paragraphs[0].add_run(f"{NAME}  ·  {EMAIL}  ·  Page 1"), spec, size=8)
            _font(section.header.paragraphs[0].add_run(f"Resume of {NAME}"), spec, size=8)
        self.header()
        if spec.layout == "two_col":
            table = self.add_t(1, 2)
            _no_borders(table)
            left, right = table.rows[0].cells
            left.width, right.width = Inches(2.2), Inches(_text_width(spec) - 2.2)
            for cell in (left, right):
                self._unused_cells.add(id(cell._tc))
            for entry in spec.sections:
                title, kind = entry[0], entry[1]
                self.container = left if len(entry) > 2 and entry[2] == "L" else right
                self.first_section = False
                self.section(title, kind)
        elif spec.layout == "rows":
            table = self.add_t(len(spec.sections), 1)
            _no_borders(table)
            for row, (title, kind) in zip(table.rows, spec.sections):
                self.use_cell(row.cells[0])
                self.first_section = True
                self.section(title, kind)
        else:
            for title, kind, *_ in spec.sections:
                self.section(title, kind)
        if spec.fragment:
            self._fragment_runs()
        if spec.nbsp:
            self._nbsp()
        if spec.sdt:
            self._wrap_in_content_controls()
        self.doc.save(str(path))
        return path

    # -- post-processors that mimic what real editors leave behind --------------------------------------
    def _fragment_runs(self) -> None:
        import copy
        import re as _re

        for run in list(self.doc.element.body.iter(qn("w:r"))):
            nodes = [c for c in run if c.tag == qn("w:t")]
            if len(nodes) != 1 or len(run) > 2 or not nodes[0].text or " " not in nodes[0].text.strip():
                continue
            pieces = _re.findall(r"\S+\s*|\s+", nodes[0].text)
            if len(pieces) < 2:
                continue
            anchor = run
            nodes[0].text = pieces[0]
            nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            for piece in pieces[1:]:
                clone = copy.deepcopy(run)
                clone.find(qn("w:t")).text = piece
                clone.find(qn("w:t")).set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                anchor.addnext(clone)
                if len(piece) > 3:  # a bookmark / spell-check marker between runs, as editors do
                    marker = OxmlElement("w:proofErr")
                    marker.set(qn("w:type"), "spellStart")
                    anchor.addnext(marker)
                    anchor = marker
                anchor = clone

    def _nbsp(self) -> None:
        for node in self.doc.element.body.iter(qn("w:t")):
            if node.text and " " in node.text and len(node.text) > 12:
                node.text = node.text.replace(" ", "\u00a0", 1).replace(" ", "  ", 1)
                node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    def _wrap_in_content_controls(self) -> None:
        body = self.doc.element.body
        targets = [p for p in body.findall(qn("w:p")) if p.find(qn("w:r")) is not None][:1]
        for p in body.findall(qn("w:p")):  # headings: bold-only short paragraphs
            text = "".join(t.text or "" for t in p.iter(qn("w:t")))
            if 0 < len(text.split()) <= 4 and p.find(".//" + qn("w:b")) is not None and p not in targets:
                targets.append(p)
        for p in targets:
            sdt = OxmlElement("w:sdt")
            pr = OxmlElement("w:sdtPr")
            alias = OxmlElement("w:alias")
            alias.set(qn("w:val"), "Resume field")
            pr.append(alias)
            sdt.append(pr)
            content = OxmlElement("w:sdtContent")
            sdt.append(content)
            p.addprevious(sdt)
            content.append(p)


# ----- the corpus ---------------------------------------------------------------------------------------------------
EXP = [("Summary", "paragraph"), ("Skills", "skills"), ("Experience", "experience"), ("Education", "education")]
EXP2 = [("Professional Summary", "paragraph"), ("Technical Skills", "skills"), ("Work Experience", "experience"),
        ("Education", "education"), ("Certifications", "bullets")]
EXP3 = [("Profile", "paragraph"), ("Core Competencies", "skills"), ("Professional Experience", "experience"),
        ("Education", "education"), ("Achievements", "bullets")]
FRESH = [("Career Objective", "paragraph"), ("Education", "education"), ("Technical Skills", "skills"),
         ("Academic Projects", "projects"), ("Achievements", "bullets")]
FRESH2 = [("Objective", "paragraph"), ("Education", "education"), ("Projects", "projects"), ("Internship", "experience"),
          ("Skills", "skills"), ("Extracurricular Activities", "bullets"), ("Declaration", "declaration")]
FRESH3 = [("Summary", "paragraph"), ("Skills", "skills"), ("Education", "education"), ("Projects", "projects"),
          ("Certifications", "bullets"), ("Languages", "inline")]

CORPUS: list[Spec] = [
    # experienced -----------------------------------------------------------------------------------------------
    Spec("exp01", "experienced", header="centered", heading="border_caps", bullet="list_style", dates="tab", skills="labels", sections=EXP),
    Spec("exp02", "experienced", header="left", heading="heading1", bullet="list_style", dates="tab", skills="labels", font="Arial", size=10.5, sections=EXP2),
    Spec("exp03", "experienced", header="table", heading="shaded", bullet="glyph", dates="table", skills="table", font="Georgia", size=10, sections=EXP3),
    Spec("exp04", "experienced", header="stacked", heading="colored", bullet="square", dates="tab", skills="bullets", font="Cambria", sections=EXP2),
    Spec("exp05", "experienced", header="title", heading="plain_bold", bullet="list_style", dates="nextline", skills="labels", font="Times New Roman", size=12, sections=EXP),
    Spec("exp06", "experienced", header="centered", heading="sep_paragraph", bullet="arrow", dates="pipe", skills="dash", sections=EXP2, icons=True),
    Spec("exp07", "experienced", header="left", heading="underline", bullet="dash", dates="paren", skills="comma", sections=EXP3, date_style="short"),
    Spec("exp08", "experienced", header="centered", heading="caps_plain", bullet="glyph", dates="comma", skills="labels", font="Verdana", size=9.5, sections=EXP, date_style="numeric"),
    Spec("exp09", "experienced", header="table", heading="border_caps", bullet="list_style", dates="tab", skills="labels", sections=EXP2, hyperlinks=True),
    Spec("exp10", "experienced", header="left", heading="heading2", bullet="list_style", dates="table", skills="bullets", font="Calibri", size=11, sections=EXP3, date_style="year", icons=True),
    Spec("exp11", "experienced", header="centered", heading="colored", bullet="glyph", dates="nextline", skills="table", sections=EXP, hyperlinks=True),
    Spec("exp12", "experienced", header="stacked", heading="sep_paragraph", bullet="list_style", dates="tab", skills="dash", font="Garamond", size=11.5, sections=EXP2, date_style="short"),
    # freshers --------------------------------------------------------------------------------------------------------
    Spec("fr01", "fresher", header="centered", heading="border_caps", bullet="list_style", dates="tab", skills="labels", sections=FRESH),
    Spec("fr02", "fresher", header="left", heading="shaded", bullet="glyph", dates="table", skills="bullets", font="Arial", size=10, sections=FRESH2),
    Spec("fr03", "fresher", header="title", heading="heading1", bullet="list_style", dates="nextline", skills="table", sections=FRESH3),
    Spec("fr04", "fresher", header="stacked", heading="colored", bullet="arrow", dates="pipe", skills="comma", font="Cambria", sections=FRESH),
    Spec("fr05", "fresher", header="table", heading="plain_bold", bullet="square", dates="tab", skills="labels", font="Times New Roman", size=12, sections=FRESH2, date_style="year"),
    Spec("fr06", "fresher", header="centered", heading="underline", bullet="dash", dates="paren", skills="dash", sections=FRESH3, date_style="year"),
    Spec("fr07", "fresher", header="left", heading="caps_plain", bullet="list_style", dates="comma", skills="labels", font="Verdana", size=9.5, sections=FRESH, date_style="numeric"),
    Spec("fr08", "fresher", header="centered", heading="sep_paragraph", bullet="glyph", dates="tab", skills="bullets", sections=FRESH2, icons=True, hyperlinks=True),
    Spec("fr09", "fresher", header="stacked", heading="heading2", bullet="list_style", dates="table", skills="table", font="Georgia", size=10.5, sections=FRESH3, date_style="short"),
    Spec("fr10", "fresher", header="left", heading="border_caps", bullet="arrow", dates="tab", skills="comma", sections=FRESH, date_style="short"),
]

CREATIVE = [("What I Do", "paragraph"), ("Where I Have Worked", "experience"), ("What I Know", "skills"),
            ("Where I Studied", "education")]
TWOCOL = [("Skills", "skills", "L"), ("Education", "education", "L"), ("Languages", "inline", "L"),
          ("Summary", "paragraph"), ("Experience", "experience"), ("Projects", "projects")]
FRESH4 = [("Education", "education"), ("Skills", "skills"), ("Internships", "experience"), ("Projects", "projects"),
          ("Training", "bullets"), ("Hobbies", "inline"), ("References", "references")]

CORPUS += [
    Spec("exp13", "experienced", header="left", heading="border_caps", bullet="list_style", dates="tab", skills="labels", sections=TWOCOL, layout="two_col", size=10),
    Spec("exp14", "experienced", header="centered", heading="plain_bold", bullet="list_style", dates="tab", skills="labels", sections=EXP2, layout="rows"),
    Spec("exp15", "experienced", header="left", heading="shaded", bullet="list_style", dates="tab", skills="labels", sections=EXP3, heading_row=True),
    Spec("exp16", "experienced", header="centered", heading="border_caps", bullet="list_style", dates="tab", skills="labels", sections=EXP2, footer=True, name_style="credentials"),
    Spec("exp17", "experienced", header="left", heading="border_caps", bullet="list_style", dates="pipe", skills="bullets", sections=EXP, numbered=True),
    Spec("exp18", "experienced", header="centered", heading="colored", bullet="glyph", dates="tab", skills="labels", sections=EXP2, mixed_bullets=True, name_style="allcaps"),
    Spec("exp19", "experienced", header="left", heading="border_caps", bullet="list_style", dates="tab", skills="labels", sections=CREATIVE),
    Spec("exp20", "experienced", header="stacked", heading="shaded", bullet="list_style", dates="table", skills="dash", sections=EXP3, footer=True, hyperlinks=True),
    Spec("fr11", "fresher", header="left", heading="border_caps", bullet="glyph", dates="tab", skills="labels", sections=FRESH4),
    Spec("fr12", "fresher", header="centered", heading="plain_bold", bullet="list_style", dates="paren", skills="comma", sections=FRESH4, date_style="year", footer=True),
    Spec("fr13", "fresher", header="left", heading="colored", bullet="list_style", dates="table", skills="table", sections=FRESH3, layout="two_col", size=10),
    Spec("fr14", "fresher", header="table", heading="heading1", bullet="square", dates="nextline", skills="bullets", sections=FRESH2, layout="rows", date_style="numeric"),
    Spec("fr15", "fresher", header="centered", heading="underline", bullet="list_style", dates="tab", skills="labels", sections=FRESH, numbered=True, icons=True),
    Spec("fr16", "fresher", header="stacked", heading="caps_plain", bullet="arrow", dates="comma", skills="table", sections=FRESH4, mixed_bullets=True, name_style="allcaps"),
]

CORPUS += [
    Spec("wild01", "experienced", header="left", heading="border_caps", bullet="list_style", dates="tab", skills="labels", sections=EXP2, fragment=True),
    Spec("wild02", "experienced", header="centered", heading="plain_bold", bullet="glyph", dates="paren", skills="bullets", sections=EXP, fragment=True, date_style="short"),
    Spec("wild03", "experienced", header="left", heading="border_caps", bullet="list_style", dates="tab", skills="labels", sections=EXP2, sdt=True),
    Spec("wild04", "fresher", header="centered", heading="caps_plain", bullet="list_style", dates="pipe", skills="dash", sections=FRESH2, colon=True),
    Spec("wild05", "experienced", header="centered", heading="underline", bullet="list_style", dates="tab", skills="labels", sections=EXP3, colon=True),
    Spec("wild06", "experienced", header="left", heading="border_caps", bullet="glyph", dates="tab", skills="labels", sections=EXP2, nbsp=True, fragment=True),
    Spec("wild07", "fresher", header="stacked", heading="shaded", bullet="list_style", dates="table", skills="labels", sections=FRESH, sdt=True, fragment=True),
    Spec("wild08", "experienced", header="table", heading="border_caps", bullet="list_style", dates="nextline", skills="comma", sections=EXP2, fragment=True, footer=True),
]

CORPUS += [
    Spec("wild09", "experienced", header="left", heading="border_caps", bullet="list_style", dates="left", skills="labels", sections=EXP2),
    Spec("wild10", "experienced", header="centered", heading="plain_bold", bullet="numpr", dates="tab", skills="bullets", sections=EXP3),
    Spec("wild11", "fresher", header="left", heading="colored", bullet="numpr", dates="left", skills="labels", sections=FRESH2, date_style="short"),
]


def build_corpus(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    return {spec.id: Builder(spec).build(folder / f"{spec.id}.docx") for spec in CORPUS}
