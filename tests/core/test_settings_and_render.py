"""v4 settings: schema/store, filename + duplicate helpers, dynamic rendering, Writer/Settings/Profile UI."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

_TEST_ROOT = tempfile.mkdtemp(prefix="rw-v4-settings-")

from docx import Document  # noqa: E402

from resume_core.render import (  # noqa: E402
    ResumeContent,
    ResumeFormat,
    SectionSpec,
    build_output_filename,
    find_duplicate_files,
    split_keywords,
)
from resume_core.settings import (  # noqa: E402
    SETTING_DEFS,
    Settings,
    SettingsError,
    categories,
    settings_in_category,
)


def _paragraph_texts(path: Path) -> list[str]:
    return [p.text for p in Document(str(path)).paragraphs if p.text.strip()]


class SettingsStoreTests(unittest.TestCase):
    def test_defaults_round_trip_through_json(self) -> None:
        settings = Settings()
        again = Settings.from_json(settings.to_json())
        self.assertEqual(settings.to_dict(), again.to_dict())

    def test_unknown_key_and_bad_values_are_rejected(self) -> None:
        with self.assertRaises(SettingsError):
            Settings.from_json('{"output": {"nope": 1}}')
        with self.assertRaises(SettingsError):
            Settings.from_json("{not json")
        settings = Settings()
        for key, bad in (
            ("output.filename_template", "NoCompanyPlaceholder"),
            ("output.filename_template", "{company}{bogus}"),
            ("appearance.accent_color", "not-a-colour"),
            ("appearance.editor_font_size", 3),
            ("fonts.font_choices", []),
            ("fonts.body_size_choices", ["big"]),
            ("duplicate_check.enabled", "yes"),
        ):
            with self.assertRaises(SettingsError, msg=f"{key}={bad!r}"):
                settings.set(key, bad)

    def test_sections_validation(self) -> None:
        settings = Settings()
        rows = settings.get("sections.items")
        rows.append(dict(rows[0]))  # duplicate key
        with self.assertRaises(SettingsError):
            settings.set("sections.items", rows)
        rows = settings.get("sections.items")
        rows[0]["key"] = "Bad Key!"
        with self.assertRaises(SettingsError):
            settings.set("sections.items", rows)
        rows = settings.get("sections.items")
        rows[0]["min_words"], rows[0]["max_words"] = 60, 20
        with self.assertRaises(SettingsError):
            settings.set("sections.items", rows)
        # Failed sets leave the stored value untouched.
        self.assertEqual(settings.get("sections.items")[0]["key"], "summary")

    def test_listeners_and_reset(self) -> None:
        settings = Settings()
        seen: list[tuple[str, ...]] = []
        settings.add_listener(seen.append)
        settings.set("personal.name", "  Ada Lovelace ")
        self.assertEqual(settings.get("personal.name"), "Ada Lovelace")
        self.assertFalse(settings.is_default("personal.name"))
        settings.reset("personal.name")
        self.assertTrue(settings.is_default("personal.name"))
        self.assertEqual(seen, [("personal.name",), ("personal.name",)])

    def test_categories_and_settings_are_alphabetical(self) -> None:
        names = categories()
        self.assertEqual(names, sorted(names, key=str.casefold))
        self.assertNotIn("Backup", names)  # Backup is a docked bar for administrators, not a settings category
        for category in names:
            labels = [d.label for d in settings_in_category(category)]
            self.assertEqual(labels, sorted(labels, key=str.casefold), category)
        for expected in ("Appearance", "Duplicate Check", "Education", "Fonts", "Metadata", "Output",
                         "Personal Details", "Resume Sections", "Validation"):
            self.assertIn(expected, names)
        self.assertEqual(len({d.key for d in SETTING_DEFS}), len(SETTING_DEFS))


class BackupNameTests(unittest.TestCase):
    def test_name_is_resw_ritbkp_year_month_day(self) -> None:
        from resume_core.backup import backup_basename

        self.assertEqual(backup_basename(date(2026, 11, 11)), "ResWritBkp2026Nov11")
        self.assertEqual(backup_basename(date(2027, 1, 5)), "ResWritBkp2027Jan05")
        self.assertEqual(backup_basename(date(2026, 12, 31)), "ResWritBkp2026Dec31")
        self.assertRegex(backup_basename(), r"^ResWritBkp\d{4}[A-Z][a-z]{2}\d{2}$")


class ColorParsingTests(unittest.TestCase):
    def test_accepted_colour_formats(self) -> None:
        from resume_core.settings.colors import parse_color

        for text, expected in (
            ("#FF8800", "#ff8800"), ("ff8800", "#ff8800"), ("#f80", "#ff8800"),
            ("rgb(255, 136, 0)", "#ff8800"), ("RGB(255,136,0)", "#ff8800"), ("255 136 0", "#ff8800"),
            ("255,136,0", "#ff8800"), ("rgb(100%, 0%, 0%)", "#ff0000"), ("hsl(0, 100%, 50%)", "#ff0000"),
            ("Orange", "#ffa500"), ("  white ", "#ffffff"),
        ):
            self.assertEqual(parse_color(text), expected, text)
        for bad in ("", "rgb(300, 0, 0)", "#12345", "rgb(1, 2)", "banana"):
            with self.assertRaises(ValueError, msg=bad):
                parse_color(bad)

    def test_setting_normalises_colour(self) -> None:
        settings = Settings()
        settings.set("appearance.accent_color", "rgb(10, 20, 30)")
        self.assertEqual(settings.get("appearance.accent_color"), "#0a141e")


class OutputHelperTests(unittest.TestCase):
    def test_filename_placeholders(self) -> None:
        day = date(2026, 11, 9)
        self.assertEqual(build_output_filename("Acme Inc!", today=day), "ResumeAcmeInc09Nov.docx")
        self.assertEqual(build_output_filename("", today=day), "ResumeXXX09Nov.docx")
        self.assertEqual(
            build_output_filename(
                "Acme", template="{name}_{company}_{date}_{username}", date_format="%Y%m%d",
                name="Ada Lovelace", username="ada", today=day,
            ),
            "AdaLovelace_Acme_20261109_ada.docx",
        )
        self.assertEqual(build_output_filename("", placeholder="TBD", today=day), "ResumeTBD09Nov.docx")

    def test_duplicate_finder_options(self) -> None:
        root = Path(tempfile.mkdtemp(dir=_TEST_ROOT))
        applied = root / "#applied"
        applied.mkdir()
        (root / "ResumeAcme09Nov.docx").write_bytes(b"x")
        (applied / "old-ACME.PDF").write_bytes(b"x")
        (applied / "acme.txt").write_bytes(b"x")
        dirs = [root, applied, root, root / "missing"]
        found = find_duplicate_files(dirs, "acme")
        self.assertEqual(sorted(p.name for p in found), ["ResumeAcme09Nov.docx", "old-ACME.PDF"])
        self.assertEqual(find_duplicate_files(dirs, "acme", case_sensitive=True), [])
        self.assertEqual(
            [p.name for p in find_duplicate_files(dirs, "acme", extensions=[".txt"])], ["acme.txt"]
        )
        self.assertEqual(find_duplicate_files(dirs, "   "), [])
        self.assertEqual(find_duplicate_files([applied], "acme", extensions=["pdf"])[0].name, "old-ACME.PDF")

    def test_split_keywords_limit(self) -> None:
        self.assertEqual(split_keywords("a, b\nc; d, e, f"), ["a", "b", "c", "d", "e"])
        self.assertEqual(split_keywords("a, b, c", limit=2), ["a", "b"])
        self.assertEqual(split_keywords("a, b, c", limit=0), [])


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "formats"
YCK_RESUME = FIXTURE_DIR / "YcKResume.docx"


class DynamicRenderTests(unittest.TestCase):
    """Section plans rendered through an uploaded sample (YcKResume: Title Case headings, separators, tabbed rows)."""

    def _build(self, content: ResumeContent) -> Path:
        from resume_core.render.template import build_resume_from_template

        out = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "out.docx"
        build_resume_from_template(content, ResumeFormat(template_path=YCK_RESUME), out)
        return out

    def test_custom_section_order_headings_and_hidden_sections(self) -> None:
        plan = (
            SectionSpec("projects", "Projects", "bullets", heading="SELECTED PROJECTS"),
            SectionSpec("summary", "Summary", "paragraph"),
            SectionSpec("empty_one", "Nothing Here", "bullets"),
        )
        content = ResumeContent(
            name="Ada Lovelace", email="ada@example.com", phone="", location="London",
            sections={"projects": "- Analytical Engine notes", "summary": "Mathematician.", "hidden": "SHOULD NOT APPEAR"},
            section_plan=plan,
        )
        texts = _paragraph_texts(self._build(content))
        self.assertEqual(texts[0], "Ada Lovelace")
        self.assertEqual(texts[1], "ada@example.com  |  London")  # blank phone leaves no dangling separator
        self.assertLess(texts.index("SELECTED PROJECTS"), texts.index("Summary"))
        self.assertTrue(any("Analytical Engine notes" in t for t in texts))
        self.assertNotIn("SHOULD NOT APPEAR", "\n".join(texts))
        self.assertNotIn("Nothing Here", "\n".join(texts))  # empty sections are skipped entirely
        self.assertNotIn("Yashashchandra", "\n".join(texts))

    def test_blank_name_is_dropped(self) -> None:
        content = ResumeContent(name="", email="", phone="+1 555 0100", location="", sections={"s": "x"},
                                section_plan=(SectionSpec("s", "S", "paragraph"),))
        texts = _paragraph_texts(self._build(content))
        self.assertEqual(texts[0], "+1 555 0100")

    def test_known_companies_fill_missing_dates_from_settings(self) -> None:
        companies = ({
            "name": "Acme", "aliases": ["acme corp"], "default_date": "May 2020 – Present",
            "role_dates": ["January 2022 – Present", "May 2020 – December 2021"],
        },)
        content = ResumeContent(
            name="A", email="", phone="", location="",
            sections={"experience": "Acme Corp | Remote\nSenior Engineer\nBuilt things.\nEngineer\nBuilt more things."},
            section_plan=(SectionSpec("experience", "Experience", "experience", heading="WORK"),),
            known_companies=companies,
        )
        texts = _paragraph_texts(self._build(content))
        self.assertIn("Acme Corp  |  Remote\tMay 2020 – Present", texts)
        self.assertIn("Senior Engineer\tJanuary 2022 – Present", texts)
        self.assertIn("Engineer\tMay 2020 – December 2021", texts)

    def test_without_known_companies_undated_lines_become_bullets(self) -> None:
        content = ResumeContent(
            name="A", email="", phone="", location="",
            sections={"experience": "Acme Corp | Remote\nSenior Engineer"},
            section_plan=(SectionSpec("experience", "Experience", "experience"),),
        )
        texts = _paragraph_texts(self._build(content))
        self.assertFalse([t for t in texts if "\t" in t and re.search(r"\d{4}", t)])
        self.assertIn("•\tAcme Corp | Remote", texts)

    def test_metadata_settings_are_applied(self) -> None:
        content = ResumeContent(
            name="Ada Lovelace", email="", phone="", location="",
            sections={"summary": "x", "kw": "a, b, c, d"},
            section_plan=(SectionSpec("summary", "Summary", "paragraph"),),
            keywords_text="a, b, c, d", author="A. Lovelace", subject="CV", title_template="{name} - CV",
            keyword_count=3,
        )
        core = Document(str(self._build(content))).core_properties
        self.assertEqual(core.author, "A. Lovelace")
        self.assertEqual(core.subject, "CV")
        self.assertEqual(core.title, "Ada Lovelace - CV")
        self.assertEqual(core.keywords, "a, b, c")

    def test_legacy_content_renders_the_samples_own_sections(self) -> None:
        content = ResumeContent(
            name="Ada", email="a@example.com", phone="", location="", summary="Hello.",
            skills="Python: yes", experience="Acme | Remote January 2024 - Present\nBuilt it.",
            certifications="", top_skills="x, y", education_entries=("State U\tMay 2018 – May 2022",),
        )
        texts = _paragraph_texts(self._build(content))
        for heading in ("Summary", "Skills", "Professional Experience", "Education"):
            self.assertIn(heading, texts)

    def test_font_and_size_choices_are_applied(self) -> None:
        from resume_core.render.template import build_resume_from_template

        content = ResumeContent(name="Ada", email="", phone="", location="", summary="Hello.",
                                section_plan=(SectionSpec("summary", "Summary", "paragraph"),))
        same = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "same.docx"
        build_resume_from_template(content, ResumeFormat(template_path=YCK_RESUME, font_name="Arial",
                                                         name_size=16, heading_size=12, body_size=11), same)
        changed = Path(tempfile.mkdtemp(dir=_TEST_ROOT)) / "changed.docx"
        build_resume_from_template(content, ResumeFormat(template_path=YCK_RESUME, font_name="Georgia",
                                                         name_size=20, heading_size=12, body_size=11), changed)
        sizes = lambda path: [r.font.size.pt for r in Document(str(path)).paragraphs[0].runs if r.font.size]  # noqa: E731
        fonts = lambda path: {r.font.name for p in Document(str(path)).paragraphs for r in p.runs if r.text.strip()}  # noqa: E731
        self.assertEqual(sizes(same), [16.0])
        self.assertEqual(sizes(changed), [20.0])
        self.assertEqual(fonts(same), {"Arial"})
        self.assertEqual(fonts(changed), {"Georgia"})


if __name__ == "__main__":
    unittest.main()
