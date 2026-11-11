"""OOXML analysis + template-faithful generation, and per-format settings."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import re
import tempfile
import unittest
from pathlib import Path

_TEST_ROOT = tempfile.mkdtemp(prefix="rw-ooxml-")

from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT  # noqa: E402
from docx.shared import Inches, Pt  # noqa: E402
from lxml import etree  # noqa: E402

from resume_core.ooxml.analysis import analyze_document  # noqa: E402
from resume_core.ooxml.sample import sample_sections  # noqa: E402
from resume_core.ooxml.xmlutil import PPR, RPR, iter_paragraphs, paragraph_text, text_items  # noqa: E402
from resume_core.render import ResumeContent, ResumeFormat, SectionSpec  # noqa: E402
from resume_core.render.parse import normalize_date_text  # noqa: E402
from resume_core.render.template import build_resume_from_template  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "formats"
CLEAN = ("YcKResume", "YcKResumeFTR2")
ALL = (*CLEAN, "YcKITFTR1")


def _canon(element) -> str:
    if element is None:
        return ""
    text = etree.tostring(element).decode()
    return re.sub(r' w:rsid\w*="[^"]*"| w14:paraId="[^"]*"| w14:textId="[^"]*"| xmlns:\w+="[^"]*"', "", text)


def _fingerprint(paragraph):
    items = [i for i in text_items(paragraph) if i.kind == "t" and (i.element.text or "").strip()]
    return _canon(paragraph.find(PPR)), _canon(items[0].run.find(RPR) if items else None), bool(items)


def _sample_content(path: Path, **overrides) -> ResumeContent:
    """The sample's own text, expressed the way a user would type it into the Writer."""
    sections = sample_sections(analyze_document(Document(str(path))))
    plan = tuple(SectionSpec(s["key"], s["label"], s["kind"], "", s["has_heading"]) for s in sections)
    texts = {s["key"]: s["text"] for s in sections}
    education = texts.pop("education", "")
    values = dict(
        name="Jane Doe", email="jane@example.org", phone="+1 555 010 2030", location="Austin, TX",
        sections=texts, section_plan=plan, education_entries=(education,) if education else (),
    )
    values.update(overrides)
    return ResumeContent(**values)


def _generate(path: Path, content: ResumeContent) -> Document:
    out = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "out.docx"
    build_resume_from_template(content, ResumeFormat(template_path=path), out)
    return Document(str(out))


class AnalysisTests(unittest.TestCase):
    def test_sections_headings_and_kinds(self) -> None:
        a = analyze_document(Document(str(FIXTURES / "YcKResume.docx")))
        self.assertEqual([(r.key, r.heading_text, r.kind) for r in a.regions], [
            ("summary", "Summary", "paragraph"),
            ("skills", "Skills", "skills"),
            ("experience", "Professional Experience", "experience"),
            ("education", "Education", "education"),
        ])
        self.assertTrue(a.uses_separators)
        self.assertEqual(a.contact_separator, "  |  ")
        self.assertTrue(a.is_linear)
        self.assertEqual({"company", "role", "bullet", "gap"} - set(a.region_for("experience").exemplars), set())

        ftr2 = analyze_document(Document(str(FIXTURES / "YcKResumeFTR2.docx")))
        self.assertEqual(ftr2.region_for("summary").heading_text, "PROFESSIONAL SUMMARY")
        self.assertIsNotNone(ftr2.tagline)
        self.assertFalse(ftr2.uses_separators)
        self.assertEqual(ftr2.name_size, 24)

    def test_table_layout_without_summary_heading(self) -> None:
        a = analyze_document(Document(str(FIXTURES / "YcKITFTR1.docx")))
        self.assertFalse(a.is_linear)  # headings live in different table rows
        summary = a.region_for("summary")
        self.assertFalse(summary.has_heading)
        self.assertEqual([r.key for r in a.regions], ["summary", "experience", "education", "skills"])
        self.assertEqual(a.region_for("skills").kind, "skills")
        # A company line + its separate date line are one logical unit.
        self.assertEqual(a.region_for("experience").lines[0].role, "unit")
        self.assertEqual(len(a.region_for("experience").lines[0].blocks), 2)

    def test_dates_with_to_in_month_names_survive_normalisation(self) -> None:
        self.assertEqual(normalize_date_text("October 2020 to Present"), "October 2020 – Present")
        self.assertEqual(normalize_date_text("May 2012-June 2014"), "May 2012 – June 2014")


class FidelityTests(unittest.TestCase):
    def test_sample_text_reproduces_every_sample_format(self) -> None:
        """Generate from the sample's own text: nothing invented, nothing lost (clean samples)."""
        for name in CLEAN:
            path = FIXTURES / f"{name}.docx"
            sample = Document(str(path))
            sample_fp = [_fingerprint(p) for p in iter_paragraphs(sample.element.body)]
            tagline = analyze_document(sample).tagline  # blank tagline setting removes that line on purpose
            out_fp = [_fingerprint(p) for p in iter_paragraphs(_generate(path, _sample_content(path)).element.body)]
            self.assertEqual([i for i, f in enumerate(out_fp) if f not in set(sample_fp)], [], name)
            lost = [i for i, f in enumerate(sample_fp) if f[2] and f not in set(out_fp)]
            allowed = {0} if tagline is None else {1}
            self.assertLessEqual(set(lost), allowed, name)

    def test_page_setup_styles_and_package_parts_are_kept(self) -> None:
        for name in ALL:
            path = FIXTURES / f"{name}.docx"
            source, result = Document(str(path)), _generate(path, _sample_content(path))
            for attr in ("page_width", "page_height", "top_margin", "left_margin", "right_margin", "bottom_margin"):
                self.assertEqual(getattr(source.sections[0], attr), getattr(result.sections[0], attr), (name, attr))
            self.assertEqual(_canon(source.styles.element), _canon(result.styles.element), name)
            self.assertEqual(len(source.tables), len(result.tables), name)

    def test_header_replaced_and_no_sample_personal_data_left(self) -> None:
        for name in ALL:
            path = FIXTURES / f"{name}.docx"
            sample_text = "\n".join(paragraph_text(p) for p in iter_paragraphs(Document(str(path)).element.body))
            result = _generate(path, _sample_content(path))
            texts = [paragraph_text(p) for p in iter_paragraphs(result.element.body)]
            joined = "\n".join(texts)
            self.assertIn("Jane Doe", texts[0], name)
            self.assertIn("jane@example.org", joined, name)
            self.assertIn("Austin, TX", joined, name)
            self.assertNotIn("Yashashchandra", joined, name)
            self.assertNotIn("gmail.com", joined, name)
            self.assertNotIn("897", joined, name)
            self.assertIn("Yashashchandra", sample_text)

    def test_two_column_skills_layout_is_kept(self) -> None:
        path = FIXTURES / "YcKITFTR1.docx"
        skills = "\n".join(f"Group {i}: item {i}" for i in range(1, 7))
        content = _sample_content(path)
        content = ResumeContent(**{**content.__dict__, "sections": {**content.sections, "skills": skills}})
        result = _generate(path, content)
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        last_row = list(result.element.body.iter(ns + "tr"))[-1]
        columns = [[paragraph_text(p) for p in cell.iter(ns + "p")] for cell in last_row.findall(ns + "tc")]
        self.assertEqual(len(columns), 2)
        self.assertEqual([len(c) for c in columns], [3, 3])
        self.assertEqual(columns[0][0], "Group 1: item 1")
        self.assertEqual(columns[1][0], "Group 4: item 4")

    def test_any_content_any_amount(self) -> None:
        """More/fewer jobs and bullets, blank contact items, extra and hidden sections."""
        experience = "\n".join([
            "Acme Corp | Remote   October 2020 - Present", "- Led a team of 5",
            "- Cut costs — by 30%", "Small Co | NYC   2016 - 2019", "- Wrote code", "- More code",
            "Mid Co | Paris | May 2012 to June 2014", "- stuff", "- things", "- items", "- more",
        ])
        for name in ALL:
            path = FIXTURES / f"{name}.docx"
            plan = (
                SectionSpec("experience", "Experience", "experience"),
                SectionSpec("summary", "Summary", "paragraph"),
                SectionSpec("projects", "Projects", "bullets", heading="SIDE PROJECTS"),
                SectionSpec("education", "Education", "education"),
            )
            content = ResumeContent(
                name="Zed Quux", email="zed@example.org", phone="", location="", section_plan=plan,
                sections={"experience": experience, "summary": "Short.", "projects": "- One\n- Two"},
                education_entries=("MIT\tMay 2014 – May 2018\nBS Computer Science", "Harvard\t2018 – 2020"),
            )
            result = _generate(path, content)
            joined = "\n".join(paragraph_text(p) for p in iter_paragraphs(result.element.body))
            for expected in ("Zed Quux", "zed@example.org", "Acme Corp", "October 2020 – Present", "Mid Co",
                             "May 2012 – June 2014", "Cut costs, by 30%", "SIDE PROJECTS", "Harvard", "2018 – 2020",
                             "BS Computer Science"):
                self.assertIn(expected, joined, (name, expected))
            for gone in ("Yashashchandra", "gmail.com", "Hyderabad", "DBS", "Python", "Skills", "SKILLS"):
                self.assertNotIn(gone, joined, (name, gone))
            # still a valid package that python-docx can reopen
            out = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "again.docx"
            result.save(str(out))
            self.assertTrue(Document(str(out)).paragraphs)

    def test_linear_formats_follow_settings_order(self) -> None:
        path = FIXTURES / "YcKResume.docx"
        content = _sample_content(path)
        plan = tuple(reversed(content.section_plan))
        texts = [paragraph_text(p) for p in iter_paragraphs(_generate(
            path, ResumeContent(**{**content.__dict__, "section_plan": plan})).element.body)]
        self.assertLess(texts.index("Education"), texts.index("Professional Experience"))
        self.assertLess(texts.index("Professional Experience"), texts.index("Summary"))

    def test_hidden_empty_and_headingless_sections(self) -> None:
        path = FIXTURES / "YcKResume.docx"
        content = _sample_content(path)
        content = ResumeContent(**{**content.__dict__, "sections": {**content.sections, "skills": ""}})
        texts = [paragraph_text(p) for p in iter_paragraphs(_generate(path, content).element.body)]
        self.assertNotIn("Skills", texts)  # empty section is omitted entirely
        plan = tuple(SectionSpec(s.key, s.label, s.kind, "", False) if s.key == "summary" else s
                     for s in _sample_content(path).section_plan)
        texts = [paragraph_text(p) for p in iter_paragraphs(_generate(
            path, ResumeContent(**{**_sample_content(path).__dict__, "section_plan": plan})).element.body)]
        self.assertNotIn("Summary", texts)

    def test_contact_hyperlinks_follow_new_values(self) -> None:
        path = FIXTURES / "YcKResume.docx"
        result = _generate(path, _sample_content(path))
        targets = [rel.target_ref for rel in result.part.rels.values() if rel.is_external]
        self.assertIn("mailto:jane@example.org", targets)

    def test_blank_name_and_tagline_handling(self) -> None:
        path = FIXTURES / "YcKResumeFTR2.docx"
        with_tagline = _generate(path, _sample_content(path, tagline="Platform Engineer"))
        texts = [paragraph_text(p) for p in iter_paragraphs(with_tagline.element.body)]
        self.assertIn("Platform Engineer", texts)
        self.assertNotIn("DevOps & Cloud", "\n".join(texts))


class SelectedTypographyTests(unittest.TestCase):
    """Whatever the sample uses, the font and sizes chosen in the Writer are what the document contains."""

    @staticmethod
    def _sizes(path: Path, *, font: str, name: int, heading: int, body: int) -> dict[str, set[int]]:
        from resume_core.ooxml.styles import StyleSheet

        out = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "o.docx"
        build_resume_from_template(_sample_content(path), ResumeFormat(
            template_path=path, font_name=font, name_size=name, heading_size=heading, body_size=body), out)
        document = Document(str(out))
        sheet = StyleSheet(document)
        headings = {"summary", "skills", "work experience", "professional experience", "professional summary",
                    "education", "certifications"}
        groups: dict[str, set[int]] = {"name": set(), "heading": set(), "body": set()}
        fonts: set[str] = set()
        for index, paragraph in enumerate(iter_paragraphs(document.element.body)):
            text = paragraph_text(paragraph).strip().lower()
            group = "name" if index == 0 else "heading" if text in headings else "body"
            for item in text_items(paragraph):
                if item.kind == "t" and (item.element.text or "").strip():
                    fmt = sheet.run_format(item.run, paragraph)
                    groups[group].add(fmt.size_half_pts)
                    fonts.add(fmt.font)
        groups["fonts"] = fonts  # type: ignore[assignment]
        return groups

    def test_every_sample_gets_exactly_the_selected_sizes_and_font(self) -> None:
        for name in ("YcKResume", "YcKResumeFTR2"):
            path = FIXTURES / f"{name}.docx"
            for body in (9, 10, 11, 12, 13):
                got = self._sizes(path, font="Georgia", name=22, heading=14, body=body)
                self.assertEqual(got["body"], {body * 2}, (name, body))
                self.assertEqual(got["heading"], {28}, (name, body))
                self.assertEqual(got["name"], {44}, (name, body))
                self.assertEqual(got["fonts"], {"Georgia"}, (name, body))

    def test_selecting_the_samples_own_values_still_writes_them(self) -> None:
        path = FIXTURES / "YcKResumeFTR2.docx"  # body 9 / 9.5 pt: the dropdown shows 10 and 10 is what you get
        analysis = analyze_document(Document(str(path)))
        got = self._sizes(path, font=analysis.font_name, name=analysis.name_size,
                          heading=analysis.heading_size, body=analysis.body_size)
        self.assertEqual(got["body"], {analysis.body_size * 2})

    def test_table_layout_and_bullet_marks_follow_the_selection(self) -> None:
        path = FIXTURES / "YcKITFTR1.docx"
        got = self._sizes(path, font="Calibri", name=26, heading=15, body=11)
        self.assertEqual(got["body"], {22})
        self.assertEqual(got["fonts"], {"Calibri"})
        out = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "o.docx"
        build_resume_from_template(_sample_content(path), ResumeFormat(
            template_path=path, font_name="Calibri", name_size=26, heading_size=15, body_size=11), out)
        marks = [p.find(PPR).find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr")
                 for p in iter_paragraphs(Document(str(out)).element.body) if p.find(PPR) is not None]
        self.assertTrue(all(m is not None for m in marks))  # paragraph marks (bullet glyph size) set too


class ImplicitFormattingTests(unittest.TestCase):
    """A sample where body text has no explicit size or font anywhere (Word then uses 10 pt and the theme font)."""

    @staticmethod
    def _build(path: Path) -> None:
        from docx.oxml.ns import qn

        document = Document()
        styles = document.styles.element
        for node in list(styles.iter(qn("w:sz"), qn("w:szCs"))):
            node.getparent().remove(node)  # no size in any style or default
        for tag in ("w:rFonts",):
            for node in list(styles.iter(qn(tag))):
                for attribute in list(node.attrib):
                    del node.attrib[attribute]
                node.set(qn("w:asciiTheme"), "minorHAnsi")  # font only from the theme
                node.set(qn("w:hAnsiTheme"), "minorHAnsi")
        name = document.add_paragraph()
        name.add_run("Pat Sample").bold = True
        document.add_paragraph("pat@sample.com | +1 555 0100 | Boston")
        heading = document.add_paragraph()
        heading.add_run("Summary").bold = True
        document.add_paragraph("A long enough summary sentence to count as regular body text in the sample document.")
        heading = document.add_paragraph()
        heading.add_run("Skills").bold = True
        skill = document.add_paragraph()
        skill.add_run("Languages: ").bold = True
        skill.add_run("Python, Go, Rust and other languages for the sample")
        document.save(str(path))

    def test_unsized_text_is_read_as_ten_points_and_theme_font_is_resolved(self) -> None:
        path = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "implicit.docx"
        self._build(path)
        analysis = analyze_document(Document(str(path)))
        self.assertEqual(analysis.body_size, 10)
        self.assertEqual(analysis.body_half_pts, 20)
        self.assertTrue(analysis.font_name)  # resolved from the theme, not guessed

    def test_choosing_a_body_size_applies_to_text_that_had_no_size(self) -> None:
        from resume_core.ooxml.styles import StyleSheet

        path = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "implicit.docx"
        self._build(path)
        analysis = analyze_document(Document(str(path)))
        content = ResumeContent(
            name="Ana Test", email="ana@test.org", phone="", location="Oslo",
            sections={"summary": "A long enough summary sentence to count as regular body text.",
                      "skills": "Languages: Python, Go"},
            section_plan=(SectionSpec("summary", "Summary", "paragraph"), SectionSpec("skills", "Skills", "skills")),
        )

        def body_sizes(body_size: int, font: str) -> tuple[set[int], int]:
            out = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "o.docx"
            build_resume_from_template(content, ResumeFormat(
                template_path=path, font_name=font, name_size=analysis.name_size,
                heading_size=analysis.heading_size, body_size=body_size), out)
            document = Document(str(out))
            sheet = StyleSheet(document)
            sizes, explicit_fonts = set(), 0
            for paragraph in list(iter_paragraphs(document.element.body))[1:]:
                for item in text_items(paragraph):
                    if item.kind == "t" and (item.element.text or "").strip():
                        sizes.add(sheet.run_format(item.run, paragraph).size_half_pts)
                        fonts = item.run.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr")
                        explicit_fonts += int(fonts is not None and b"w:ascii=" in etree.tostring(fonts))
            return sizes, explicit_fonts

        for chosen in (9, 10, 11, 12):
            sizes, _fonts = body_sizes(chosen, "Cambria")
            self.assertEqual(sizes - {analysis.heading_size * 2}, {chosen * 2} if chosen * 2 != analysis.heading_size * 2 else set(), chosen)
            self.assertIn(chosen * 2, sizes)

    def test_uploaded_format_typography_comes_from_the_sample_itself(self) -> None:
        from resume_core.formats import analyze_sample

        path = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "implicit.docx"
        self._build(path)
        info, defaults = analyze_sample(path.read_bytes())
        self.assertEqual(info["body_size"], 10)  # unsized text is 10 pt in Word, not a guess of 11
        self.assertIn(10, defaults["fonts.body_size_choices"])


class UnknownFormatTests(unittest.TestCase):
    """A sample built from scratch with different styles, headings and layout."""

    @staticmethod
    def _build_sample(path: Path) -> None:
        document = Document()
        section = document.sections[0]
        section.left_margin = section.right_margin = Inches(1)
        name = document.add_paragraph()
        name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = name.add_run("Sam Sample")
        run.bold, run.font.size = True, Pt(22)
        contact = document.add_paragraph("sam@sample.com  ·  +44 20 7946 0958  ·  London")
        contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
        document.add_heading("Technical Proficiencies", level=1)
        skill = document.add_paragraph()
        skill.add_run("Languages: ").bold = True
        skill.add_run("Python, Go")
        document.add_heading("Employment History", level=1)
        row = document.add_paragraph()
        row.paragraph_format.tab_stops.add_tab_stop(Inches(6.5), WD_TAB_ALIGNMENT.RIGHT)
        row.add_run("Widgets Ltd, London").bold = True
        row.add_run("\tMarch 2019 – Present")
        document.add_paragraph("Built the widget pipeline.", style="List Bullet")
        document.add_paragraph("Reduced build time by half.", style="List Bullet")
        document.add_heading("Leadership", level=1)
        document.add_paragraph("Chaired the engineering guild.", style="List Bullet")
        document.add_heading("Education", level=1)
        edu = document.add_paragraph()
        edu.paragraph_format.tab_stops.add_tab_stop(Inches(6.5), WD_TAB_ALIGNMENT.RIGHT)
        edu.add_run("BSc Physics, UCL").bold = True
        edu.add_run("\t2012 – 2015")
        document.save(str(path))

    def test_unseen_layout_is_understood_and_reproduced(self) -> None:
        path = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "unknown.docx"
        self._build_sample(path)
        analysis = analyze_document(Document(str(path)))
        self.assertEqual([r.key for r in analysis.regions], ["skills", "experience", "volunteering", "education"])
        self.assertEqual([r.kind for r in analysis.regions], ["skills", "experience", "bullets", "education"])
        content = ResumeContent(
            name="Ana Example", email="ana@example.net", phone="+1 555 0100", location="Oslo",
            section_plan=(
                SectionSpec("skills", "Skills", "skills"),
                SectionSpec("experience", "Experience", "experience"),
                SectionSpec("volunteering", "Leadership", "bullets"),
                SectionSpec("education", "Education", "education"),
            ),
            sections={
                "skills": "Tools: git, docker\nCloud: AWS",
                "experience": "Acme AS | Oslo   June 2021 - Present\n- Shipped things\nOldCo | Bergen   2018 - 2021\n- Did stuff",
                "volunteering": "- Mentor\n- Speaker",
            },
            education_entries=("NTNU\t2014 – 2018",),
        )
        result = _generate(path, content)
        paragraphs = list(iter_paragraphs(result.element.body))
        texts = [paragraph_text(p) for p in paragraphs]
        self.assertEqual(texts[0], "Ana Example")
        self.assertIn("ana@example.net  ·  +1 555 0100  ·  Oslo", texts)
        self.assertIn("Acme AS | Oslo\tJune 2021 – Present", texts)
        self.assertIn("OldCo | Bergen\t2018 – 2021", texts)
        self.assertNotIn("Sam", "\n".join(texts))
        # Heading and row formatting come from the sample's own paragraphs.
        by_text = {paragraph_text(p): p for p in paragraphs}
        sample = {paragraph_text(p): p for p in iter_paragraphs(Document(str(path)).element.body)}
        self.assertEqual(_canon(by_text["Employment History"].find(PPR)), _canon(sample["Employment History"].find(PPR)))
        self.assertEqual(_fingerprint(by_text["Acme AS | Oslo\tJune 2021 – Present"]),
                         _fingerprint(sample["Widgets Ltd, London\tMarch 2019 – Present"]))
        self.assertEqual(_fingerprint(by_text["Tools: git, docker"]), _fingerprint(sample["Languages: Python, Go"]))


def _two_row_table_sample(path: Path) -> None:
    """Company + first role share ONE two-row table; later roles are single-row tables (dates in column 2)."""
    document = Document()

    def heading(text: str, size: int) -> None:
        run = document.add_paragraph().add_run(text)
        run.bold, run.font.size = True, Pt(size)

    heading("Your Name", 14)
    document.add_paragraph("your.name@example.com  |  +1 555 010 0100  |  City, State")
    heading("WORK EXPERIENCE", 12)

    def table(rows):
        t = document.add_table(rows=len(rows), cols=2)
        for row, (left, right) in zip(t.rows, rows):
            row.cells[0].text, row.cells[1].text = left, right

    table([("Company Name | Location", "January 2020 – Present"), ("Software Engineer", "September 2023 – July 2024")])
    document.add_paragraph("Sample bullet point describing an achievement.")
    table([("Software Developer", "July 2022 – September 2023")])
    document.add_paragraph("Another sample bullet point about your work.")
    heading("EDUCATION", 12)
    table([("Degree Name", "January 2016 – May 2020")])
    document.add_paragraph("Institution Name, City, State")
    document.save(str(path))


class TwoRowTableExperienceTests(unittest.TestCase):
    def test_company_and_role_rows_are_filled_from_their_own_lines(self):
        path = Path(_TEST_ROOT) / "two_row.docx"
        _two_row_table_sample(path)
        experience = "\n".join([
            "Acme Corp | Austin, TX    June 2026 – Present",
            "Site Reliability Engineer",  # role written without dates
            "Triaged escalated incidents and coordinated cross-team fixes within SLA windows.",
            "",
            "Globex | Remote    July 2022 – July 2024",
            "Platform Engineer – Analyst    September 2023 – July 2024",
            "Earned two awards across multiple quarters in 2023–2024, recognised for incident resolution.",
            "Platform Engineer – I    July 2022 – September 2023",
            "Built Java APIs for customer service operations.",
        ])
        education = "Master of Science    August 2024 – May 2026\nSome University, AL"
        content = ResumeContent(
            name="Jane Doe", email="jane@example.org", phone="+1 555 010 2030", location="Austin, TX",
            sections={"experience": experience},
            section_plan=(SectionSpec("experience", "Work Experience", "experience", "WORK EXPERIENCE", True),
                          SectionSpec("education", "Education", "education", "EDUCATION", True)),
            education_entries=(education, education),  # an accidental duplicate entry prints once
        )
        result = _generate(path, content)
        text = "\n".join(paragraph_text(p) for p in iter_paragraphs(result.element.body))
        for leaked in ("Software Engineer", "Software Developer", "Company Name", "Degree Name", "Institution Name"):
            self.assertNotIn(leaked, text)  # sample text never leaks
        pairs = [(c[0].strip(), c[1].strip()) for c in ([cell.text for cell in row.cells] for t in result.tables for row in t.rows)]
        self.assertEqual(pairs, [
            ("Acme Corp | Austin, TX", "June 2026 – Present"),
            ("Site Reliability Engineer", ""),
            ("Globex | Remote", "July 2022 – July 2024"),
            ("Platform Engineer – Analyst", "September 2023 – July 2024"),
            ("Platform Engineer – I", "July 2022 – September 2023"),
            ("Master of Science", "August 2024 – May 2026"),
        ])
        # A bullet that merely mentions a year range stays a bullet.
        self.assertIn("Earned two awards across multiple quarters in 2023–2024, recognised for incident resolution.",
                      [paragraph_text(p) for p in iter_paragraphs(result.element.body)])


if __name__ == "__main__":
    unittest.main()
