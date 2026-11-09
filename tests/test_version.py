"""Tests for version parse/compare and Release asset naming helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from resume_writer.constants import APP_VERSION
from resume_writer.version import (
    asset_name_for_platform,
    asset_names_for,
    compact_version_slug,
    compare_versions,
    display_app_name,
    display_name,
    is_newer,
    macos_asset_name,
    normalize_version,
    parse_version,
    pyinstaller_name,
    version_is_newer,
    windows_asset_name,
)


class VersionHelpersTests(unittest.TestCase):
    def test_app_version_is_canonical(self) -> None:
        self.assertEqual(normalize_version(APP_VERSION), APP_VERSION)
        self.assertEqual(parse_version(APP_VERSION), (3, 0, 0))
        self.assertRegex(APP_VERSION, r"^v3\.0\.0(?:Beta\d+)?$")

    def test_normalize_accepts_optional_leading_v(self) -> None:
        self.assertEqual(normalize_version("3.1.2"), "v3.1.2")
        self.assertEqual(normalize_version("v3.1.2"), "v3.1.2")

    def test_normalize_accepts_beta_n(self) -> None:
        self.assertEqual(normalize_version("v3.0.0Beta2"), "v3.0.0Beta2")
        self.assertEqual(normalize_version("3.0.0Beta2"), "v3.0.0Beta2")
        self.assertEqual(normalize_version("v3.0.0beta2"), "v3.0.0Beta2")
        self.assertEqual(normalize_version("v1.2.3Beta10"), "v1.2.3Beta10")

    def test_normalize_rejects_bad_forms(self) -> None:
        for bad in ("", "v3", "v3.0", "3.0.0-beta", "vv3.0.0", "version-3"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    normalize_version(bad)

    def test_parse_and_compare(self) -> None:
        self.assertEqual(parse_version("v2.1.0"), (2, 1, 0))
        self.assertEqual(parse_version("v3.0.0Beta2"), (3, 0, 0))
        self.assertEqual(compare_versions("v3.0.0", "v3.0.0"), 0)
        self.assertEqual(compare_versions("v2.9.9", "v3.0.0"), -1)
        self.assertEqual(compare_versions("v3.0.1", "v3.0.0"), 1)
        self.assertEqual(compare_versions("3.0.0", "v3.0.0"), 0)
        # Pre-release label sorts before the plain release
        self.assertEqual(compare_versions("v3.0.0-beta", "v3.0.0"), -1)

    def test_compare_beta_n_ordering(self) -> None:
        # BetaN < same X.Y.Z release; higher N is newer among betas.
        self.assertEqual(compare_versions("v3.0.0Beta1", "v3.0.0Beta2"), -1)
        self.assertEqual(compare_versions("v3.0.0Beta2", "v3.0.0Beta1"), 1)
        self.assertEqual(compare_versions("v3.0.0Beta2", "v3.0.0Beta2"), 0)
        self.assertEqual(compare_versions("v3.0.0Beta2", "v3.0.0"), -1)
        self.assertEqual(compare_versions("v3.0.0", "v3.0.0Beta2"), 1)
        # Numeric Beta compare (not string): Beta2 < Beta10
        self.assertEqual(compare_versions("v3.0.0Beta2", "v3.0.0Beta10"), -1)
        self.assertTrue(is_newer("v3.0.0", "v3.0.0Beta2"))
        self.assertTrue(is_newer("v3.0.0Beta2", "v3.0.0Beta1"))
        self.assertFalse(is_newer("v3.0.0Beta2", "v3.0.0"))

    def test_is_newer(self) -> None:
        self.assertTrue(is_newer("v3.0.1", "v3.0.0"))
        self.assertFalse(is_newer("v3.0.0", "v3.0.0"))
        self.assertFalse(is_newer("v2.9.0", "v3.0.0"))
        self.assertTrue(version_is_newer("v3.1.0", "v3.0.0"))
        self.assertTrue(is_newer("v99.0.0"))
        self.assertFalse(is_newer("v1.0.0"))

    def test_display_and_pyinstaller_names(self) -> None:
        self.assertEqual(display_name("v3.0.0"), "Resume Writer v3.0.0")
        self.assertEqual(display_app_name("v3.0.0"), "Resume Writer v3.0.0")
        self.assertEqual(pyinstaller_name("v3.0.0"), "Resume Writer v3.0.0")
        self.assertEqual(display_name("v3.0.0Beta2"), "Resume Writer v3.0.0Beta2")
        self.assertEqual(display_name(), f"Resume Writer {APP_VERSION}")

    def test_asset_names_include_leading_v(self) -> None:
        self.assertEqual(compact_version_slug("v3.0.0"), "ResumeWriterv3.0.0")
        self.assertEqual(macos_asset_name("v3.0.0"), "ResumeWriterv3.0.0.app.zip")
        self.assertEqual(windows_asset_name("v3.0.0"), "ResumeWriterv3.0.0.exe.zip")
        self.assertEqual(
            asset_names_for("v3.0.0"),
            {
                "macos": "ResumeWriterv3.0.0.app.zip",
                "windows": "ResumeWriterv3.0.0.exe.zip",
            },
        )
        self.assertEqual(
            macos_asset_name("v3.0.0Beta2"),
            "ResumeWriterv3.0.0Beta2.app.zip",
        )
        self.assertEqual(
            windows_asset_name("v3.0.0Beta2"),
            "ResumeWriterv3.0.0Beta2.exe.zip",
        )
        self.assertEqual(macos_asset_name(), f"ResumeWriter{APP_VERSION}.app.zip")
        self.assertEqual(windows_asset_name(), f"ResumeWriter{APP_VERSION}.exe.zip")
        self.assertEqual(
            asset_name_for_platform("v3.0.0", "darwin"),
            "ResumeWriterv3.0.0.app.zip",
        )
        self.assertEqual(
            asset_name_for_platform("v3.0.0", "win32"),
            "ResumeWriterv3.0.0.exe.zip",
        )
        self.assertEqual(
            asset_name_for_platform("v3.0.0Beta2", "darwin"),
            "ResumeWriterv3.0.0Beta2.app.zip",
        )


if __name__ == "__main__":
    unittest.main()
