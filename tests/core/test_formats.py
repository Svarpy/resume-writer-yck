"""resume_core.formats: what an uploaded sample teaches the app."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import unittest
from pathlib import Path

from resume_core.formats import FormatError, FormatInfo, analyze_sample

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "formats"


class AnalyzeSampleTests(unittest.TestCase):
    def test_info_and_settings_defaults_come_from_the_sample(self) -> None:
        info, defaults = analyze_sample((FIXTURES / "YcKResumeFTR2.docx").read_bytes())
        self.assertEqual(info["font_name"], "Arial")
        self.assertEqual(info["name_size"], 24)
        self.assertEqual([s["heading"] for s in info["sections"]],
                         ["PROFESSIONAL SUMMARY", "SKILLS", "WORK EXPERIENCE", "EDUCATION"])
        keys = [row["key"] for row in defaults["sections.items"]]
        self.assertEqual(keys, ["summary", "skills", "experience", "education", "top_skills"])
        self.assertEqual(defaults["sections.items"][-1]["kind"], "keywords")
        self.assertIn("file_name", defaults["validation.required_fields"])
        self.assertNotIn("education", defaults["validation.required_fields"])
        self.assertIn(24, defaults["fonts.name_size_choices"])

    def test_table_layout_sample_without_a_summary_heading(self) -> None:
        info, defaults = analyze_sample((FIXTURES / "YcKITFTR1.docx").read_bytes())
        summary = defaults["sections.items"][0]
        self.assertEqual((summary["key"], summary["heading"], summary["show_heading"]), ("summary", "", False))
        self.assertEqual([s["key"] for s in info["sections"]], ["summary", "experience", "education", "skills"])

    def test_rejects_things_that_are_not_resumes(self) -> None:
        for bad in (b"", b"plain text", b"PK\x03\x04 not really a docx"):
            with self.assertRaises(FormatError):
                analyze_sample(bad)

    def test_format_info_round_trip(self) -> None:
        info, _defaults = analyze_sample((FIXTURES / "YcKResume.docx").read_bytes())
        restored = FormatInfo.from_dict({"id": "x", "name": "Ref", **info, "unknown": 1})
        self.assertEqual(restored.typography()["body_size"], 11)
        self.assertEqual(FormatInfo.from_dict(restored.to_dict()), restored)


if __name__ == "__main__":
    unittest.main()
