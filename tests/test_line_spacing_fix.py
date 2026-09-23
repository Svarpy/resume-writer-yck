"""Regression: exact Word line spacing must not overflow int32 on generate."""

from __future__ import annotations


# Ensure repo root is importable when tests live under tests/.
import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import tempfile
import unittest
from pathlib import Path

_TEST_ROOT = tempfile.mkdtemp(prefix="rw-linespacing-")
os.environ["RESUME_WRITER_DATA_DIR"] = _TEST_ROOT

from docx.shared import Twips  # noqa: E402

from formats_store import (  # noqa: E402
    add_format_from_docx,
    extract_format_from_docx,
    normalize_line_spacing,
    set_primary_format,
)
from user_auth import signup, set_current_user  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "formats" / "YcKITFTR1.docx"
DESKTOP = Path("/Users/yck/Desktop/CLGENAPPL/base/YcKITFTR1.docx")


class LineSpacingNormalizeTests(unittest.TestCase):
    def test_twips_exact_becomes_multiplier(self) -> None:
        # 240 twips == single-line exact == 152400 EMUs
        self.assertAlmostEqual(normalize_line_spacing(Twips(240)), 1.0, places=3)
        self.assertAlmostEqual(normalize_line_spacing(152400), 1.0, places=3)
        self.assertEqual(normalize_line_spacing(1.15), 1.15)

    def test_itftr1_extract_and_generate(self) -> None:
        path = FIXTURE if FIXTURE.exists() else DESKTOP
        if not path.exists():
            self.skipTest("YcKITFTR1.docx fixture not available")
        signup("linespacing", "Passw0rd1")
        set_current_user("linespacing")
        spec = extract_format_from_docx(path, name="ITFTR1")
        self.assertLessEqual(spec.line_spacing, 3.0)
        self.assertGreaterEqual(spec.line_spacing, 0.5)
        saved = add_format_from_docx("linespacing", path, "ITFTR1")
        set_primary_format("linespacing", saved.id)
        from resume_writer_app import (
            DEFAULT_MASTERS_EDUCATION,
            ResumeContent,
            build_resume,
            resume_format_from_store,
        )

        fmt = resume_format_from_store("linespacing")
        self.assertLessEqual(fmt.line_spacing, 3.0)
        out = Path(_TEST_ROOT) / "itftr1-out.docx"
        build_resume(
            ResumeContent(
                name="Test",
                email="t@e.com",
                phone="1",
                location="ATL",
                summary=("word " * 45).strip(),
                skills="Python",
                experience="Acme | Atlanta, GA | January 2025 - May 2026\nBuilt things.",
                certifications="",
                top_skills="a,b,c,d,e",
                education_entries=(DEFAULT_MASTERS_EDUCATION,),
            ),
            fmt,
            out,
        )
        self.assertTrue(out.is_file())
        self.assertGreater(out.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()