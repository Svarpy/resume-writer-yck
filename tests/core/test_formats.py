"""resume_core.formats: what an uploaded template teaches the app."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import unittest
from pathlib import Path

from docx import Document

from resume_core.formats import FormatError, FormatInfo, analyze_template

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "templates"


class AnalyzeTemplateTests(unittest.TestCase):
    def test_info_and_settings_defaults_come_from_the_template(self) -> None:
        info, defaults = analyze_template((FIXTURES / "rsr.docx").read_bytes())
        self.assertEqual(info["font_name"], "Georgia")
        self.assertEqual(info["name_size"], 18)
        self.assertEqual([s["heading"] for s in info["sections"]],
                         ["PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "PROFESSIONAL WORK EXPERIENCE", "EDUCATION"])
        self.assertIn("experience > jobs(company, location) > roles(title, dates) > bullets(text)", info["outline"])
        keys = [row["key"] for row in defaults["sections.items"]]
        self.assertEqual(keys, ["summary", "skills", "experience", "education", "top_skills"])
        self.assertEqual(defaults["sections.items"][-1]["kind"], "keywords")
        self.assertIn("file_name", defaults["validation.required_fields"])
        self.assertNotIn("education", defaults["validation.required_fields"])
        self.assertIn(18, defaults["fonts.name_size_choices"])
        self.assertIn("Georgia", defaults["fonts.font_choices"])

    def test_headingless_sections_are_not_shown_with_a_heading(self) -> None:
        _info, defaults = analyze_template((FIXTURES / "rama.docx").read_bytes())
        rows = {row["key"]: row for row in defaults["sections.items"]}
        self.assertEqual((rows["summary"]["heading"], rows["summary"]["show_heading"]), ("", False))
        self.assertEqual((rows["education"]["heading"], rows["education"]["show_heading"]), ("", False))
        self.assertTrue(rows["skills"]["show_heading"])
        self.assertEqual([r["key"] for r in defaults["sections.items"][:4]],
                         ["summary", "education", "skills", "experience"])

    def test_rejects_things_that_are_not_templates(self) -> None:
        for bad in (b"", b"plain text", b"PK\x03\x04 not really a docx"):
            with self.assertRaises(FormatError):
                analyze_template(bad)

    def test_a_plain_sample_is_rejected_with_a_helpful_message(self) -> None:
        path = Path(__file__).with_name("_plain_sample.docx")
        document = Document()
        document.add_paragraph("Jane Roe")
        document.add_paragraph("SUMMARY")
        document.save(str(path))
        try:
            with self.assertRaises(FormatError) as raised:
                analyze_template(path.read_bytes())
        finally:
            path.unlink()
        self.assertIn("placeholders", str(raised.exception))

    def test_every_problem_is_listed(self) -> None:
        path = Path(__file__).with_name("_bad_template.docx")
        document = Document()
        for text in ("{{name}}", "{{#summary}}{{wibble}}", "{{company}}"):
            document.add_paragraph(text)
        document.save(str(path))
        try:
            with self.assertRaises(FormatError) as raised:
                analyze_template(path.read_bytes())
        finally:
            path.unlink()
        joined = " ".join(raised.exception.errors)
        for fragment in ("unknown field {{wibble}}", "outside any block", "never closed"):
            self.assertIn(fragment, joined)

    def test_format_info_round_trip(self) -> None:
        info, _defaults = analyze_template((FIXTURES / "ycksample.docx").read_bytes())
        restored = FormatInfo.from_dict({"id": "x", "name": "Ref", **info, "unknown": 1})
        self.assertEqual(restored.typography()["body_size"], 10)
        self.assertEqual(FormatInfo.from_dict(restored.to_dict()), restored)


if __name__ == "__main__":
    unittest.main()
