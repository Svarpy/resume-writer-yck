"""Sanitising an uploaded sample must remove personal text without changing what the format produces."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import io
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document
from lxml import etree

from resume_core.formats import analyze_sample
from resume_core.ooxml.analysis import analyze_document
from resume_core.ooxml.xmlutil import iter_paragraphs, paragraph_text
from resume_core.render import ResumeContent, ResumeFormat, SectionSpec
from resume_core.render.template import build_resume_from_template
from resume_core.sanitize import sanitize_sample

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "formats"
NAMES = ("YcKResume", "YcKResumeFTR2", "YcKITFTR1")
PERSONAL = (rb"Yashashchandra", rb"Kollu", rb"gmail", rb"yashash", rb"2058977790", rb"205\) 897", rb"DBS",
            rb"Hyderabad", rb"Birmingham", rb"Value Labs", rb"Alabama", rb"Regions Bank")


def _all_bytes(data: bytes) -> list[tuple[str, bytes]]:
    archive = zipfile.ZipFile(io.BytesIO(data))
    return [(name, archive.read(name)) for name in archive.namelist()]


def _content(path: Path) -> ResumeContent:
    """A realistic resume: more of everything than the sample (jobs, bullets, skills, education)."""
    plan = tuple(SectionSpec(r.key, r.heading_text or r.key, r.kind) for r in analyze_document(Document(str(path))).regions)
    experience = "\n".join([
        "Acme Corp | Remote   May 2020 - Present", "Senior Engineer   May 2021 - Present", "- Led a team of five",
        "- Cut costs by 30%", "Small Co | NYC   2016 - 2019", "Engineer   2016 - 2019", "- Wrote code",
        "- Reviewed code", "- Mentored interns",
    ])
    return ResumeContent(
        name="Jane Doe", email="jane@example.org", phone="+1 555 010 2030", location="Austin, TX",
        tagline="Platform Engineer", section_plan=plan,
        sections={"summary": "A summary line.\nA second line.", "skills": "Languages: Go, Rust\nTools: git, make\nCloud: AWS",
                  "experience": experience, "certifications": "- AWS SAA", "projects": "- Thing"},
        education_entries=("MIT\tMay 2014 – May 2018\nBS Computer Science", "Harvard\t2018 – 2020"),
    )


def _generate(template: Path, content: ResumeContent) -> Path:
    out = Path(tempfile.mkdtemp()) / "out.docx"
    build_resume_from_template(content, ResumeFormat(template_path=template), out)
    return out


def _xml_signature(path: Path) -> list[str]:
    """document.xml of a generated resume with relationship ids and rsids removed (those legitimately vary)."""
    root = etree.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    text = etree.tostring(root, method="c14n").decode("utf-8")  # canonical form: <a></a> and <a/> are the same
    return [re.sub(r' (?:w:rsid\w*|w14:paraId|w14:textId|r:id)="[^"]*"', "", text)]


class SanitizeTests(unittest.TestCase):
    def sanitized(self, name: str) -> tuple[bytes, bytes]:
        raw = (FIXTURES / f"{name}.docx").read_bytes()
        cleaned, ok = sanitize_sample(raw)
        self.assertTrue(ok, name)
        return raw, cleaned

    def test_no_personal_text_remains_anywhere_in_the_package(self) -> None:
        for name in NAMES:
            raw, cleaned = self.sanitized(name)
            self.assertTrue(any(re.search(rb"Yashashchandra", data) for _n, data in _all_bytes(raw)))
            for part, data in _all_bytes(cleaned):
                for pattern in PERSONAL:
                    self.assertIsNone(re.search(pattern, data), (name, part, pattern))
            core = Document(io.BytesIO(cleaned)).core_properties
            self.assertEqual((core.author, core.last_modified_by, core.title), ("", "", "Resume"))

    def test_same_sections_kinds_and_settings_defaults(self) -> None:
        for name in NAMES:
            raw, cleaned = self.sanitized(name)
            self.assertEqual(analyze_sample(raw)[0]["sections"], analyze_sample(cleaned)[0]["sections"], name)
            for key in ("font_name", "name_size", "heading_size", "body_size"):
                self.assertEqual(analyze_sample(raw)[0][key], analyze_sample(cleaned)[0][key], (name, key))
            self.assertEqual(analyze_sample(raw)[1]["sections.items"], analyze_sample(cleaned)[1]["sections.items"], name)

    def test_generated_resumes_are_identical_from_the_original_and_the_sanitized_sample(self) -> None:
        """The main guarantee: sanitising does not change the output for any content."""
        for name in NAMES:
            original_path = FIXTURES / f"{name}.docx"
            cleaned_path = Path(tempfile.mkdtemp()) / "clean.docx"
            cleaned_path.write_bytes(self.sanitized(name)[1])
            content = _content(original_path)
            from_original, from_clean = _generate(original_path, content), _generate(cleaned_path, content)
            self.assertEqual(_xml_signature(from_original), _xml_signature(from_clean), name)
            texts = lambda p: [paragraph_text(x) for x in iter_paragraphs(Document(str(p)).element.body)]  # noqa: E731
            self.assertEqual(texts(from_original), texts(from_clean), name)
            for part in ("word/styles.xml", "word/numbering.xml", "word/settings.xml"):
                a, b = zipfile.ZipFile(from_original), zipfile.ZipFile(from_clean)
                if part in a.namelist():
                    self.assertEqual(a.read(part), b.read(part), (name, part))

    def test_generated_resume_has_no_leftover_sample_hyperlinks(self) -> None:
        for name in NAMES:
            out = _generate(FIXTURES / f"{name}.docx", _content(FIXTURES / f"{name}.docx"))
            for part, data in _all_bytes(out.read_bytes()):
                if part.endswith(".rels"):
                    self.assertNotIn(b"gmail", data, (name, part))
                    self.assertNotIn(b"2058977790", data, (name, part))

    def test_unusable_input_is_returned_unchanged_instead_of_failing(self) -> None:
        for bad in (b"", b"not a docx", b"PK\x03\x04 truncated"):
            self.assertEqual(sanitize_sample(bad), (bad, False))


if __name__ == "__main__":
    unittest.main()
