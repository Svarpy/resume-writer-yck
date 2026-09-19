"""Smoke checks for Sprint 1 auth + formats store (no UI)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Isolate all tests from the developer's real ~/.ResumeWriter data.
_TEST_ROOT = tempfile.mkdtemp(prefix="rw-sprint1-")
os.environ["RESUME_WRITER_DATA_DIR"] = _TEST_ROOT

from formats_store import (  # noqa: E402
    DEFAULT_FORMAT_ID,
    FormatProtectedError,
    add_format_from_docx,
    create_format,
    default_format_spec,
    default_format_xml,
    delete_format,
    extract_format_from_docx,
    format_spec_from_xml,
    format_spec_to_xml,
    get_format,
    get_primary_format,
    list_formats,
    set_primary_format,
    update_format,
)
from user_auth import (  # noqa: E402
    InvalidCredentialsError,
    PasswordValidationError,
    UserExistsError,
    change_password,
    clear_session,
    get_current_user,
    get_settings,
    signin,
    signup,
    update_profile,
)


class AuthTests(unittest.TestCase):
    def test_signup_signin_change_password_and_settings(self) -> None:
        profile = signup("DemoUser", "Secret123", display_name="Demo", dark_mode=True)
        self.assertEqual(profile.username, "demouser")
        self.assertEqual(get_current_user(), "demouser")
        self.assertNotIn("password", profile.public_dict())
        self.assertTrue(profile.password_hash.startswith("$2"))

        clear_session()
        self.assertIsNone(get_current_user())
        signed = signin("DemoUser", "Secret123")
        self.assertEqual(signed.username, "demouser")

        with self.assertRaises(UserExistsError):
            signup("demouser", "Other123")

        with self.assertRaises(InvalidCredentialsError):
            signin("demouser", "wrongpass1")

        change_password("demouser", "Secret123", "Newer456")
        with self.assertRaises(InvalidCredentialsError):
            signin("demouser", "Secret123")
        signin("demouser", "Newer456")

        update_profile("demouser", dark_mode=False, primary_format_id="default")
        settings = get_settings("demouser")
        self.assertFalse(settings["dark_mode"])
        self.assertEqual(settings["primary_format_id"], "default")

    def test_password_validation(self) -> None:
        with self.assertRaises(PasswordValidationError):
            signup("shortuser", "abc")
        with self.assertRaises(PasswordValidationError):
            signup("noletter1", "12345678")


class FormatTests(unittest.TestCase):
    def setUp(self) -> None:
        if get_current_user() != "formatuser":
            try:
                signup("formatuser", "Format123")
            except UserExistsError:
                signin("formatuser", "Format123")

    def test_default_is_always_listed_and_protected(self) -> None:
        formats = list_formats("formatuser")
        self.assertEqual(formats[0].id, DEFAULT_FORMAT_ID)
        self.assertTrue(formats[0].protected)
        xml = default_format_xml()
        self.assertIn("<resumeFormat", xml)
        self.assertIn("<structure>", xml)
        self.assertIn("<heading>WORK EXPERIENCE</heading>", xml)
        with self.assertRaises(FormatProtectedError):
            update_format("formatuser", DEFAULT_FORMAT_ID, name="Nope")
        with self.assertRaises(FormatProtectedError):
            delete_format("formatuser", DEFAULT_FORMAT_ID)

    def test_crud_and_primary(self) -> None:
        created = create_format(
            "formatuser",
            "Compact",
            values={"font_name": "Calibri", "body_size": 10},
            set_as_primary=True,
        )
        self.assertEqual(get_primary_format("formatuser").id, created.id)
        self.assertEqual(get_format("formatuser", created.id).font_name, "Calibri")
        self.assertTrue(created.structure.sections)

        updated = update_format("formatuser", created.id, values={"heading_size": 14})
        self.assertEqual(updated.heading_size, 14)

        set_primary_format("formatuser", DEFAULT_FORMAT_ID)
        delete_format("formatuser", created.id)
        ids = {f.id for f in list_formats("formatuser")}
        self.assertNotIn(created.id, ids)
        self.assertEqual(get_primary_format("formatuser").id, DEFAULT_FORMAT_ID)

    def test_xml_roundtrip(self) -> None:
        spec = default_format_spec()
        restored = format_spec_from_xml(default_format_xml())
        self.assertEqual(restored.font_name, spec.font_name)
        self.assertEqual(restored.name_size, spec.name_size)
        self.assertEqual(restored.margin_top_in, spec.margin_top_in)
        self.assertEqual(
            [s.heading for s in restored.structure.sections],
            [s.heading for s in spec.structure.sections],
        )
        self.assertEqual(restored.structure.experience.left_width_in, spec.structure.experience.left_width_in)


def _add_separator_paragraph(doc) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph = doc.add_paragraph()
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def _build_structured_template(path: Path, *, font_name: str = "Calibri") -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.5)
    section.bottom_margin = Inches(0.6)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.8)

    name = doc.add_paragraph()
    run = name.add_run("Jane Doe")
    run.bold = True
    run.font.size = Pt(18)
    run.font.name = font_name

    def add_heading(text: str) -> None:
        _add_separator_paragraph(doc)
        paragraph = doc.add_paragraph()
        heading_run = paragraph.add_run(text)
        heading_run.bold = True
        heading_run.font.size = Pt(13)
        heading_run.font.name = font_name

    add_heading("SUMMARY")
    body = doc.add_paragraph()
    body_run = body.add_run("A short professional summary.")
    body_run.font.name = font_name
    body_run.font.size = Pt(11)

    add_heading("SKILLS")
    skills = doc.add_paragraph()
    skills_run = skills.add_run("Python, Word")
    skills_run.font.name = font_name

    add_heading("PROFESSIONAL EXPERIENCE")
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    left, right = table.rows[0].cells
    left.width = Inches(5.0)
    right.width = Inches(2.0)
    left.paragraphs[0].add_run("Acme Corp | Remote").bold = True
    right_para = right.paragraphs[0]
    right_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    right_run = right_para.add_run("2020 – Present")
    right_run.bold = True
    role = doc.add_paragraph()
    role_run = role.add_run("Software Engineer")
    role_run.font.name = font_name
    bullet = doc.add_paragraph(style="List Bullet")
    bullet.add_run("Shipped features").font.name = font_name

    add_heading("EDUCATION")
    edu = doc.add_paragraph()
    edu.add_run("State University").font.name = font_name

    add_heading("CERTIFICATIONS")
    cert = doc.add_paragraph()
    cert.add_run("AWS CCP").font.name = font_name

    doc.save(path)


class DocxExtractTests(unittest.TestCase):
    def test_extract_from_generated_docx(self) -> None:
        from docx import Document
        from docx.shared import Inches, Pt

        doc = Document()
        section = doc.sections[0]
        section.page_width = Inches(8.5)
        section.page_height = Inches(11)
        section.top_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        p = doc.add_paragraph()
        run = p.add_run("Sample Name")
        run.bold = True
        run.font.size = Pt(16)
        run.font.name = "Arial"

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.docx"
            doc.save(path)
            spec = extract_format_from_docx(path, name="FromDocx")
            self.assertEqual(spec.source, "docx")
            self.assertAlmostEqual(spec.page_width_in, 8.5, places=2)
            self.assertEqual(spec.name_size, 16)

            signup_name = "docxuser"
            try:
                signup(signup_name, "DocxUser1")
            except UserExistsError:
                signin(signup_name, "DocxUser1")
            saved = add_format_from_docx(signup_name, path, "Uploaded Layout")
            self.assertEqual(saved.name, "Uploaded Layout")
            self.assertFalse(saved.protected)

    def test_extract_structure_headings_separator_margins_and_experience(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "structured.docx"
            _build_structured_template(path, font_name="Calibri")
            spec = extract_format_from_docx(path, name="Structured")

            headings = {s.key: s.heading for s in spec.structure.sections}
            self.assertEqual(headings.get("summary"), "SUMMARY")
            self.assertEqual(headings.get("skills"), "SKILLS")
            self.assertEqual(headings.get("experience"), "PROFESSIONAL EXPERIENCE")
            self.assertEqual(headings.get("education"), "EDUCATION")
            self.assertIn("certifications", headings)

            self.assertTrue(spec.structure.separator.enabled)
            self.assertEqual(spec.structure.separator.sz, 12)
            self.assertEqual(spec.structure.separator.color, "000000")

            self.assertAlmostEqual(spec.margin_top_in, 0.5, places=2)
            self.assertAlmostEqual(spec.margin_left_in, 0.7, places=2)
            self.assertAlmostEqual(spec.margin_right_in, 0.8, places=2)

            experience = spec.structure.experience
            self.assertEqual(experience.company_line_mode, "two_column_table")
            self.assertGreater(experience.left_width_in, experience.right_width_in)
            self.assertEqual(experience.duration_align, "right")

            # Run-level Calibri must replace the Arial default.
            self.assertEqual(spec.font_name, "Calibri")

            restored = format_spec_from_xml(format_spec_to_xml(spec))
            self.assertEqual(restored.structure.section_for("experience").heading, "PROFESSIONAL EXPERIENCE")
            self.assertTrue(restored.structure.separator.enabled)


class WriterStructureApplyTests(unittest.TestCase):
    def test_default_format_still_emits_historical_headings(self) -> None:
        from resume_writer_app import ResumeContent, ResumeFormat, build_resume, load_docx_dependencies

        load_docx_dependencies()
        from docx import Document

        content = ResumeContent(
            name="Test User",
            email="t@example.com",
            phone="+1 555 0100",
            location="Remote",
            summary="Word " * 45,
            skills="Python: scripting",
            experience="Acme Corp | Remote\tJan 2020 – Present\nSoftware Engineer\n- Built things",
            certifications="AWS CCP",
            top_skills="Python, Word",
            education_entries=("State University\tMay 2018 – May 2022",),
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "default.docx"
            build_resume(content, ResumeFormat(), out)
            doc = Document(str(out))
            texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            self.assertIn("SUMMARY", texts)
            self.assertIn("SKILLS", texts)
            self.assertIn("WORK EXPERIENCE", texts)
            self.assertIn("EDUCATION", texts)
            self.assertIn("Certifications", texts)
            section = doc.sections[0]
            self.assertAlmostEqual(section.top_margin.inches, 0.75, places=2)

    def test_custom_structure_headings_and_margins_applied(self) -> None:
        from formats_store import DocumentStructure, ExperienceLayout, SectionRule, SeparatorStyle
        from resume_writer_app import ResumeContent, ResumeFormat, build_resume, load_docx_dependencies

        load_docx_dependencies()
        from docx import Document

        structure = DocumentStructure(
            sections=[
                SectionRule("summary", "PROFILE", True, 0),
                SectionRule("skills", "CORE SKILLS", True, 1),
                SectionRule("experience", "PROFESSIONAL EXPERIENCE", True, 2),
                SectionRule("education", "EDUCATION", True, 3),
                SectionRule("certifications", "CERTS", True, 4),
            ],
            separator=SeparatorStyle(enabled=True, sz=12, color="000000"),
            experience=ExperienceLayout(left_width_in=5.0, right_width_in=2.0, duration_align="right"),
        )
        fmt = ResumeFormat(
            font_name="Calibri",
            margin_top_in=0.5,
            margin_left_in=0.7,
            structure=structure,
        )
        content = ResumeContent(
            name="Test User",
            email="t@example.com",
            phone="+1 555 0100",
            location="Remote",
            summary="Word " * 45,
            skills="Python: scripting",
            experience="Acme Corp | Remote\tJan 2020 – Present\nSoftware Engineer\n- Built things",
            certifications="AWS CCP",
            top_skills="Python",
            education_entries=("State University\tMay 2018 – May 2022",),
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "custom.docx"
            build_resume(content, fmt, out)
            doc = Document(str(out))
            texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            self.assertIn("PROFILE", texts)
            self.assertIn("CORE SKILLS", texts)
            self.assertIn("PROFESSIONAL EXPERIENCE", texts)
            self.assertNotIn("WORK EXPERIENCE", texts)
            self.assertIn("CERTS", texts)
            self.assertAlmostEqual(doc.sections[0].top_margin.inches, 0.5, places=2)
            self.assertAlmostEqual(doc.sections[0].left_margin.inches, 0.7, places=2)
            self.assertTrue(doc.tables)
            left_w = doc.tables[0].columns[0].width
            right_w = doc.tables[0].columns[1].width
            self.assertGreater(left_w, right_w)


    def test_synthetic_section_keys_map_to_renderers(self) -> None:
        from formats_store import DocumentStructure, SectionRule, canonicalize_section_key
        from resume_writer_app import ResumeContent, ResumeFormat, build_resume, load_docx_dependencies

        self.assertEqual(canonicalize_section_key("professional_experience"), "experience")
        structure = DocumentStructure(
            sections=[
                SectionRule("summary", "SUMMARY", True, 0),
                SectionRule("skills", "SKILLS", True, 1),
                SectionRule("professional_experience", "PROFESSIONAL EXPERIENCE", True, 2),
                SectionRule("education", "EDUCATION", True, 3),
                SectionRule("certifications", "Certifications", True, 4),
            ]
        )
        self.assertEqual(structure.ordered_content_keys()[2], "experience")
        self.assertEqual(structure.section_for("experience").heading, "PROFESSIONAL EXPERIENCE")

        load_docx_dependencies()
        from docx import Document

        content = ResumeContent(
            name="Test User",
            email="t@example.com",
            phone="+1 555 0100",
            location="Remote",
            summary="Word " * 45,
            skills="Python",
            experience="Acme Corp | Remote\tJan 2020 – Present\nEngineer\n- Built",
            certifications="",
            top_skills="Python",
            education_entries=(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "synth.docx"
            build_resume(content, ResumeFormat(structure=structure), out)
            texts = [p.text.strip() for p in Document(str(out)).paragraphs if p.text.strip()]
            self.assertIn("PROFESSIONAL EXPERIENCE", texts)
            self.assertNotIn("WORK EXPERIENCE", texts)


class PrimaryFormatApplyFromReferenceTests(unittest.TestCase):
    """Regression: real PM reference docx → primary → build_resume ≠ default."""

    FIXTURE = Path(__file__).resolve().parent / "tests" / "fixtures" / "YcKResume.docx"

    def setUp(self) -> None:
        if get_current_user() != "refapplyuser":
            try:
                signup("refapplyuser", "RefApply1")
            except UserExistsError:
                signin("refapplyuser", "RefApply1")

    def test_primary_from_yckresume_differs_from_default_on_generate(self) -> None:
        from formats_store import (
            DEFAULT_FORMAT_VALUES,
            add_format_from_docx,
            default_format_spec,
            get_primary_format,
            set_primary_format,
        )
        from resume_writer_app import (
            ResumeContent,
            ResumeFormat,
            build_resume,
            load_docx_dependencies,
            resume_format_from_store,
        )

        self.assertTrue(self.FIXTURE.is_file(), f"Missing fixture: {self.FIXTURE}")
        load_docx_dependencies()
        from docx import Document

        default = default_format_spec()
        saved = add_format_from_docx(
            "refapplyuser",
            self.FIXTURE,
            "YcK Resume Primary",
            set_as_primary=True,
        )
        primary = get_primary_format("refapplyuser")
        self.assertEqual(primary.id, saved.id)
        self.assertNotEqual(primary.id, "default")

        # Template must differ from locked Default Application Format.
        self.assertAlmostEqual(primary.margin_top_in, 0.5, places=2)
        self.assertNotAlmostEqual(primary.margin_top_in, DEFAULT_FORMAT_VALUES["margin_top_in"], places=2)
        exp_rule = primary.structure.section_for("experience")
        self.assertIsNotNone(exp_rule)
        self.assertEqual(exp_rule.heading, "Professional Experience")
        self.assertNotEqual(exp_rule.heading, default.structure.section_for("experience").heading)

        fmt = resume_format_from_store("refapplyuser")
        self.assertAlmostEqual(fmt.margin_top_in, 0.5, places=2)
        self.assertEqual(fmt.structure.section_for("experience").heading, "Professional Experience")

        content = ResumeContent(
            name="Yashashchandra Kollu",
            email="y@example.com",
            phone="+1 555 0100",
            location="Remote",
            summary="Word " * 45,
            skills="Python: scripting\nWord: documents",
            experience="Acme Corp | Remote\tJan 2020 – Present\nSoftware Engineer\n- Built things",
            certifications="AWS CCP",
            top_skills="Python, Word",
            education_entries=("State University\tMay 2018 – May 2022",),
        )
        with tempfile.TemporaryDirectory() as tmp:
            custom_out = Path(tmp) / "from_primary.docx"
            default_out = Path(tmp) / "from_default.docx"
            build_resume(content, fmt, custom_out)
            build_resume(content, ResumeFormat(), default_out)

            custom_doc = Document(str(custom_out))
            default_doc = Document(str(default_out))
            custom_texts = [p.text.strip() for p in custom_doc.paragraphs if p.text.strip()]
            default_texts = [p.text.strip() for p in default_doc.paragraphs if p.text.strip()]

            self.assertIn("Professional Experience", custom_texts)
            self.assertNotIn("WORK EXPERIENCE", custom_texts)
            self.assertIn("WORK EXPERIENCE", default_texts)
            self.assertAlmostEqual(custom_doc.sections[0].top_margin.inches, 0.5, places=2)
            self.assertAlmostEqual(default_doc.sections[0].top_margin.inches, 0.75, places=2)
            self.assertNotAlmostEqual(
                custom_doc.sections[0].top_margin.inches,
                default_doc.sections[0].top_margin.inches,
                places=2,
            )

            # Title-case Summary/Skills from the reference template must win.
            self.assertIn("Summary", custom_texts)
            self.assertIn("Skills", custom_texts)
            self.assertNotEqual(custom_texts, default_texts)

        set_primary_format("refapplyuser", "default")




if __name__ == "__main__":
    unittest.main()
