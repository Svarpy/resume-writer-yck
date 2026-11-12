"""Placeholder templates: reading them, checking them, and filling them with content."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import tempfile
import unittest
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from resume_core.ooxml.xmlutil import iter_paragraphs, paragraph_text
from resume_core.placeholders import TemplateError, inspect_template
from resume_core.placeholders.api import build_resume
from resume_core.placeholders.content import education_data, experience_data, skills_data, split_dated
from resume_core.render.models import ResumeContent, ResumeFormat, SectionSpec

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "templates"
_TMP = Path(tempfile.mkdtemp(prefix="rw-placeholders-"))

EXPERIENCE = "\n".join([
    "Acme Corp | Austin, TX    June 2026 – Present",
    "Site Engineer",
    "Triaged escalated incidents and coordinated cross-team fixes within SLA windows.",
    "Built dashboards across hosts monitoring CPU, memory, latency and error rates.",
    "",
    "Globex | Remote    July 2022 – July 2024",
    "Platform Engineer – Analyst    September 2023 – July 2024",
    "Earned two awards across multiple quarters in 2023–2024, recognised for incident resolution.",
    "Platform Engineer – I    July 2022 – September 2023",
    "Built Java APIs for customer service operations.",
])
EDUCATION = "Master of Science in Physics\tAugust 2024 – May 2026\nSome University, AL  |  GPA: 4.0 / 4.0"
SKILLS = "Languages: Python, Go\nTools: git, docker"


def _plan(info) -> tuple[SectionSpec, ...]:
    return tuple(SectionSpec(s["key"], s["label"], s["kind"], s["heading"], s["show_heading"]) for s in info.sections)


def _build(template, *, experience=EXPERIENCE, education=(EDUCATION,), summary="A short summary.", skills=SKILLS,
           fmt=None, **overrides) -> Document:
    path = template if isinstance(template, Path) else FIXTURES / f"{template}.docx"
    info = inspect_template(path.read_bytes())
    texts = {"summary": summary, "skills": skills, "experience": experience}
    content = ResumeContent(
        name=overrides.pop("name", "Jane Doe"), email="jane@example.org", phone="+1 555 010 2030",
        location=overrides.pop("location", "Austin, TX"), tagline=overrides.pop("tagline", ""),
        sections={k: v for k, v in texts.items() if k in info.shape}, section_plan=_plan(info),
        education_entries=tuple(education), **overrides)
    out = Path(tempfile.mkdtemp(dir=_TMP)) / "out.docx"
    build_resume(content, fmt or ResumeFormat(template_path=path), out)
    return Document(str(out))


def _lines(document) -> list[str]:
    return [paragraph_text(p) for p in iter_paragraphs(document.element.body)]


def _text(document) -> str:
    return "\n".join(_lines(document))


class ReadingTemplates(unittest.TestCase):
    def test_the_real_templates_are_understood(self) -> None:
        expected = {
            "ycksample": ["summary", "skills", "experience", "education"],
            "rama": ["summary", "education", "skills", "experience"],
            "rsr": ["summary", "skills", "experience", "education"],
            "vitesh": ["summary", "skills", "experience", "education"],
        }
        for name, keys in expected.items():
            info = inspect_template((FIXTURES / f"{name}.docx").read_bytes())
            self.assertTrue(info.ok, (name, info.errors))
            self.assertEqual([s["key"] for s in info.sections], keys, name)
            self.assertEqual({s["key"]: s["kind"] for s in info.sections},
                             {"summary": "paragraph", "skills": "skills", "experience": "experience",
                              "education": "education"}, name)

    def test_headings_and_headingless_sections(self) -> None:
        rama = inspect_template((FIXTURES / "rama.docx").read_bytes())
        self.assertEqual({s["key"]: s["heading"] for s in rama.sections},
                         {"summary": "", "education": "", "skills": "TECHNICAL SKILLS", "experience": "WORK EXPERIENCE"})
        self.assertEqual([s["show_heading"] for s in rama.sections], [False, False, True, True])
        rsr = inspect_template((FIXTURES / "rsr.docx").read_bytes())
        self.assertEqual(rsr.sections[2]["heading"], "PROFESSIONAL WORK EXPERIENCE")

    def test_outline_and_fields(self) -> None:
        info = inspect_template((FIXTURES / "ycksample.docx").read_bytes())
        self.assertIn("experience > jobs(company, location, dates) > roles(title, dates) > bullets(text)",
                      info.outline)
        self.assertEqual(info.shape["experience"]["fields"]["roles"], ("title", "dates"))
        self.assertTrue(info.shape["education"]["grade_label"])
        self.assertGreater(info.name_size, info.body_size)

    def test_mistakes_are_reported(self) -> None:
        def make(*texts: str) -> bytes:
            document = Document()
            for text in texts:
                document.add_paragraph(text)
            path = _TMP / "bad.docx"
            document.save(str(path))
            return path.read_bytes()

        self.assertIn("never closed", " ".join(inspect_template(make("{{#summary}}", "{{text}}")).errors))
        self.assertIn("no matching", " ".join(inspect_template(make("{{text}}", "{{/summary}}")).errors))
        self.assertIn("unknown field {{wibble}}", " ".join(
            inspect_template(make("{{#summary}}{{wibble}}{{/summary}}")).errors))
        self.assertIn("outside any block", " ".join(inspect_template(make("{{company}}")).errors))
        self.assertIn("unknown block", " ".join(
            inspect_template(make("{{#summary}}{{#oops}}{{text}}{{/oops}}{{/summary}}")).errors))
        self.assertFalse(inspect_template(make("just a plain sample")).ok)
        with self.assertRaises(TemplateError):
            inspect_template(b"not a docx")

    def test_markers_split_by_word_or_typed_among_text_are_still_found(self) -> None:
        document = Document()
        paragraph = document.add_paragraph()
        for piece in ("{{#sum", "mary}}Head", "ing ", "{{te", "xt}}", " tail{{/summary}}"):
            paragraph.add_run(piece)
        path = _TMP / "split.docx"
        document.save(str(path))
        info = inspect_template(path.read_bytes())
        self.assertTrue(info.ok, info.errors)
        out = _build(path, summary="Hello there.")
        self.assertEqual(_lines(out)[0], "Heading Hello there. tail")


class FillingTemplates(unittest.TestCase):
    def test_every_template_is_filled_and_nothing_is_left_over(self) -> None:
        for name in ("ycksample", "rama", "rsr", "vitesh"):
            text = _text(_build(name))
            self.assertNotIn("{{", text, name)
            self.assertNotIn("}}", text, name)
            for needed in ("Jane Doe", "jane@example.org", "A short summary.", "Languages", "Acme Corp",
                           "Globex", "Site Engineer", "Platform Engineer – Analyst",
                           "Triaged escalated incidents", "Some University"):
                self.assertIn(needed, text, (name, needed))
            self.assertEqual(text.count("Built Java APIs"), 1, name)

    def test_a_year_range_inside_a_bullet_stays_a_bullet(self) -> None:
        text = _text(_build("rsr"))
        self.assertIn("Earned two awards across multiple quarters in 2023–2024, recognised for incident resolution.", text)

    def test_company_and_role_rows_with_their_dates(self) -> None:
        lines = _lines(_build("ycksample"))
        self.assertIn("Acme Corp Austin, TX", lines)
        self.assertIn("June 2026 – Present", lines)       # the company's dates (the role has none of its own)
        self.assertIn("Site Engineer", lines)
        self.assertIn("Platform Engineer – Analyst", lines)
        self.assertIn("September 2023 – July 2024", lines)
        self.assertIn("Platform Engineer – I", lines)
        self.assertIn("July 2022 – September 2023", lines)


    def test_a_company_without_a_role_line_loses_the_empty_role_row(self) -> None:
        document = _build("ycksample", experience="Acme Corp | Austin, TX    June 2026 – Present\nDid things.")
        rows = ["".join(cell.text for cell in row.cells) for table in document.tables for row in table.rows]
        self.assertTrue(any("Acme Corp" in r for r in rows))
        self.assertFalse([r for r in rows if r.strip() == ""])
        self.assertIn("Did things.", _lines(document))

    def test_two_roles_of_one_company_repeat_the_role_not_the_company_row(self) -> None:
        document = _build("ycksample")
        company_rows = [row for table in document.tables for row in table.rows
                        if "Globex" in "".join(c.text for c in row.cells)]
        self.assertEqual(len(company_rows), 1)

    def test_merged_company_and_role_line(self) -> None:
        lines = _lines(_build("rama"))
        self.assertIn("Site Engineer @ Acme Corp | June 2026 – Present", lines)
        self.assertIn("Platform Engineer – Analyst @ Globex | September 2023 – July 2024", lines)
        self.assertIn("Platform Engineer – I @ Globex | July 2022 – September 2023", lines)

    def test_inline_education_line_and_headingless_summary(self) -> None:
        lines = _lines(_build("rama"))
        self.assertEqual(lines[0], "Jane Doe jane@example.org | +1 555 010 2030 | Austin, TX")
        self.assertEqual(lines[1], "A short summary.")
        self.assertEqual(lines[2], "Education: Master of Science in Physics, Some University, AL")
        self.assertNotIn("SUMMARY", "\n".join(lines))

    def test_fields_the_template_does_not_have_are_ignored(self) -> None:
        text = _text(_build("vitesh"))          # no dates, no grade, no company location in Vitesh's education/job lines
        self.assertNotIn("GPA", text)
        self.assertNotIn("August 2024", text)
        self.assertIn("Acme Corp Site Engineer", text)

    def test_empty_optional_parts_take_their_separator_and_label_with_them(self) -> None:
        text = _text(_build("ycksample", education=("Diploma in Art\n2019 – 2020\nTech Institute",)))
        self.assertNotIn("GPA", text)
        lines = _lines(_build("ycksample", education=("BSc Physics\tMay 2020\nOld College",)))
        self.assertIn("Old College", lines)
        self.assertFalse([l for l in lines if l.endswith("GPA: ") or l.endswith("|  ")])

    def test_a_section_without_content_disappears_with_its_heading_and_rule(self) -> None:
        full = _build("ycksample")
        short = _build("ycksample", summary="")
        self.assertIn("SUMMARY", _text(full))
        self.assertNotIn("SUMMARY", _text(short))
        rules = lambda d: sum(1 for p in iter_paragraphs(d.element.body) if p.find(qn("w:pPr")) is not None
                              and p.find(qn("w:pPr")).find(qn("w:pBdr")) is not None)
        self.assertEqual(rules(short), rules(full) - 1)

    def test_tagline_and_missing_tagline(self) -> None:
        self.assertEqual(_lines(_build("rama", tagline="Site Reliability Engineer"))[0],
                         "Jane Doe – Site Reliability Engineer jane@example.org | +1 555 010 2030 | Austin, TX")

    def test_contact_links_are_created_by_the_app(self) -> None:
        document = _build("ycksample")
        targets = sorted(rel.target_ref for rel in document.part.rels.values() if rel.is_external)
        self.assertEqual(targets, ["mailto:jane@example.org", "tel:+15550102030"])
        self.assertEqual(len(list(document.element.iter(qn("w:hyperlink")))), 2)

    def test_writer_font_and_sizes_are_always_applied(self) -> None:
        document = _build("rsr", fmt=ResumeFormat(template_path=FIXTURES / "rsr.docx", font_name="Verdana",
                                                    name_size=20, heading_size=13, body_size=11))
        sizes = {}
        for paragraph in iter_paragraphs(document.element.body):
            text = paragraph_text(paragraph)
            sz = [r.find(qn("w:rPr")).find(qn("w:sz")).get(qn("w:val")) for r in paragraph.iter(qn("w:r"))
                  if paragraph_text(paragraph).strip() and r.find(qn("w:rPr")) is not None
                  and r.find(qn("w:rPr")).find(qn("w:sz")) is not None]
            if text.strip() and sz:
                sizes[text.strip()[:12]] = set(sz)
        self.assertEqual(sizes["Jane Doe"], {"40"})
        self.assertEqual(sizes["TECHNICAL SK"], {"26"})
        self.assertEqual(sizes["A short summ"], {"22"})
        fonts = {r.find(qn("w:rPr")).find(qn("w:rFonts")).get(qn("w:ascii")) for r in document.element.iter(qn("w:r"))
                 if r.find(qn("w:rPr")) is not None and r.find(qn("w:rPr")).find(qn("w:rFonts")) is not None}
        self.assertEqual(fonts, {"Verdana"})

    def test_template_formatting_is_untouched(self) -> None:
        """Paragraph properties come from the template; nothing is invented."""
        template = Document(str(FIXTURES / "rsr.docx"))
        known = {etree_text(p.find(qn("w:pPr"))) for p in template.element.iter(qn("w:p"))}
        result = _build("rsr")
        for paragraph in result.element.iter(qn("w:p")):
            self.assertIn(etree_text(paragraph.find(qn("w:pPr"))), known)


    def test_headings_changed_or_hidden_in_settings_are_honoured(self) -> None:
        path = FIXTURES / "ycksample.docx"
        info = inspect_template(path.read_bytes())
        plan = tuple(SectionSpec(s["key"], s["label"], s["kind"],
                                 "ABOUT ME" if s["key"] == "summary" else s["heading"],
                                 s["key"] != "skills") for s in info.sections)
        content = ResumeContent(name="Jane", email="", phone="", location="", section_plan=plan,
                                sections={"summary": "Hi.", "skills": "Tools: git"})
        out = _TMP / "headings.docx"
        build_resume(content, ResumeFormat(template_path=path), out)
        text = _text(Document(str(out)))
        self.assertIn("ABOUT ME", text)
        self.assertNotIn("SUMMARY", text)
        self.assertNotIn("SKILLS", text)
        self.assertIn("Tools", text)


    def test_text_for_a_section_the_template_lacks_is_reported_not_dropped(self) -> None:
        path = FIXTURES / "ycksample.docx"
        info = inspect_template(path.read_bytes())
        plan = (*_plan(info), SectionSpec("projects", "Projects", "bullets", "PROJECTS", True))
        content = ResumeContent(name="Jane", email="", phone="", location="", section_plan=plan,
                                sections={"summary": "Hi.", "projects": "- Built a thing"})
        with self.assertRaises(TemplateError) as raised:
            build_resume(content, ResumeFormat(template_path=path), _TMP / "x.docx")
        self.assertIn("Projects", str(raised.exception))
        self.assertIn("{{#projects}}", str(raised.exception))

    def test_metadata_is_set(self) -> None:
        document = _build("ycksample", author="Jane D.", subject="Resume", title_template="{name} Resume")
        self.assertEqual(document.core_properties.author, "Jane D.")
        self.assertEqual(document.core_properties.title, "Jane Doe Resume")

    def test_blank_metadata_stays_empty_instead_of_using_a_default(self) -> None:
        core = _build("ycksample").core_properties
        for field in ("author", "subject", "title", "keywords", "last_modified_by"):
            self.assertEqual(getattr(core, field), "", field)

    def test_no_template_means_a_clear_error(self) -> None:
        content = ResumeContent(name="x", email="", phone="", location="")
        with self.assertRaises(TemplateError):
            build_resume(content, ResumeFormat(template_path=None), _TMP / "x.docx")


def etree_text(element) -> str:
    import re

    from lxml import etree

    if element is None:
        return ""
    return re.sub(r' xmlns:\w+="[^"]*"| w:rsid\w*="[^"]*"| w14:\w+="[^"]*"', "", etree.tostring(element).decode())


class PromptAndDocs(unittest.TestCase):
    def test_the_documented_prompt_is_the_one_in_the_app(self) -> None:
        from resume_core.placeholders.prompt import AI_PROMPT

        guide = (_ROOT / "docs" / "format-templates.md").read_text(encoding="utf-8")
        self.assertIn(AI_PROMPT.rstrip(), guide)

    def test_every_documented_field_and_block_is_known(self) -> None:
        from resume_core.placeholders.prompt import AI_PROMPT
        from resume_core.placeholders.scan import BLOCK_FIELDS, INNER_BLOCKS, ROOT_FIELDS, TOKEN_RE

        for kind, name in {(m.group(1), m.group(2)) for m in TOKEN_RE.finditer(AI_PROMPT)}:
            if kind == "":
                self.assertIn(name, BLOCK_FIELDS + ROOT_FIELDS, name)
            elif name not in ("x",):
                self.assertTrue(name in INNER_BLOCKS or name in (
                    "summary", "skills", "experience", "education"), name)


class ReadingContent(unittest.TestCase):
    def test_dates_must_close_the_line(self) -> None:
        self.assertEqual(split_dated("Acme | Oslo    June 2021 – Present"), ("Acme | Oslo", "June 2021 – Present"))
        self.assertIsNone(split_dated("Earned awards in 2023–2024, recognised for results."))
        self.assertEqual(split_dated("Degree\tAugust 2020 – May 2024"), ("Degree", "August 2020 – May 2024"))

    def test_skills(self) -> None:
        items = skills_data("• Languages: Python, Go\nJust a line")["items"]
        self.assertEqual(items[0]["label"], "Languages")
        self.assertEqual(items[0]["values"], "Python, Go")
        self.assertEqual(items[1]["label"], "")
        self.assertEqual(items[1]["values"], "Just a line")

    def test_experience_structure(self) -> None:
        jobs = experience_data(EXPERIENCE)["jobs"]
        self.assertEqual([j["company"] for j in jobs], ["Acme Corp", "Globex"])
        self.assertEqual(jobs[0]["location"], "Austin, TX")
        self.assertEqual([r["title"] for r in jobs[1]["roles"]], ["Platform Engineer – Analyst", "Platform Engineer – I"])
        self.assertEqual(jobs[0]["roles"][0]["dates"], "")
        self.assertEqual(len(jobs[0]["roles"][0]["bullets"]), 2)

    def test_education_structure(self) -> None:
        degree = education_data([EDUCATION], grade_label=True)["degrees"][0]
        self.assertEqual(degree, {"degree": "Master of Science", "major": "Physics", "institution": "Some University",
                                  "location": "AL", "dates": "August 2024 – May 2026", "grade": "4.0 / 4.0"})
        plain = education_data(["Bachelor of Arts in History"], has_major=False)["degrees"][0]
        self.assertEqual(plain["degree"], "Bachelor of Arts in History")


if __name__ == "__main__":
    unittest.main()
