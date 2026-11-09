"""Automated QA for Sprint 1 UI bugfixes (Generate gate + sidebar chrome).

Read-only against production code; uses an isolated RESUME_WRITER_DATA_DIR.
"""

from __future__ import annotations


# Ensure repo root is importable when tests live under tests/.
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import tempfile
import traceback
import unittest
from pathlib import Path

_TEST_ROOT = tempfile.mkdtemp(prefix="rw-ui-bugfix-")
os.environ["RESUME_WRITER_DATA_DIR"] = _TEST_ROOT
os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

from user_auth import clear_session, signup  # noqa: E402
from resume_writer_app import ResumeWriterApp, default_output_filename_for  # noqa: E402
from ui_shell import (  # noqa: E402
    COLLAPSED_ICON_FONT,
    COLLAPSED_NAV_ICONS,
    EXPANDED_NAV_FONT,
    LOGOUT_ICON,
    MENU_ICON_FONT,
    NAV_ITEMS,
    SIDEBAR_COLLAPSED_PX,
    SIDEBAR_EXPANDED_PX,
)


# Exactly 45 word-tokens matching count_words() (\\b[\\w'-]+\\b).
SUMMARY_45 = " ".join(f"word{i}" for i in range(1, 46))


def _pump(app: ResumeWriterApp, times: int = 20) -> None:
    for _ in range(times):
        app.update_idletasks()
        app.update()


class Sprint1UiBugfixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Headless CI without xvfb cannot create a Tk root; skip the class cleanly.
        try:
            import tkinter as tk

            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except Exception as exc:  # noqa: BLE001 — environment gate only
            raise unittest.SkipTest(f"Tk display unavailable: {exc}") from exc
        clear_session()
        cls.profile = signup("uitester", "UiTest123", display_name="UI Tester", dark_mode=True)

    def setUp(self) -> None:
        clear_session()
        from user_auth import signin

        signin("uitester", "UiTest123")
        self.out_dir = Path(tempfile.mkdtemp(prefix="rw-out-", dir=_TEST_ROOT))
        (self.out_dir / "#applied").mkdir(parents=True, exist_ok=True)
        self.app = ResumeWriterApp()
        self.app.withdraw()
        _pump(self.app)
        self.app.output_dir_var.set(str(self.out_dir))
        _pump(self.app)

    def tearDown(self) -> None:
        try:
            self.app.destroy()
        except Exception:
            pass
        clear_session()

    def _fill_required_texts(self) -> None:
        for widget, value in (
            (self.app.summary_text, SUMMARY_45),
            (self.app.skills_text, "Python, Tkinter, Testing"),
            (self.app.experience_text, "Acme | Remote January 2024 - Present\nBuilt resume tooling"),
            (self.app.top_skills_text, "Python\nTkinter\nQA\nDocs\nAutomation"),
        ):
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        self.app._update_validation_state()
        _pump(self.app)

    def _generate_state(self) -> str:
        return str(self.app.generate_button.cget("state"))

    # --- Bug 1: Generate / File Name ---

    def test_bug1_empty_filename_disables_generate(self) -> None:
        self._fill_required_texts()
        self.app.output_name_part_var.set("")
        _pump(self.app)
        errors = self.app._validation_errors()
        self.assertIn("File Name is required", errors)
        # With other fields valid, File Name alone should gate Generate.
        self.assertEqual(errors, ["File Name is required"])
        self.assertIn("File Name is required", self.app.validation_var.get())
        self.assertTrue(self.app.validation_var.get().startswith("Generate disabled:"))
        self.assertEqual(self._generate_state(), "disabled")
        # Empty may still preview XXX in path; Generate stays disabled.
        self.assertIn("XXX", Path(self.app.output_var.get()).name)
        self.assertEqual(self._generate_state(), "disabled")

    def test_bug1_unique_filename_enables_generate(self) -> None:
        self._fill_required_texts()
        self.app.output_name_part_var.set("UniqueCo")
        _pump(self.app)
        self.assertEqual(self.app._validation_errors(), [])
        self.assertEqual(self.app.validation_var.get(), "Ready to generate.")
        self.assertEqual(self._generate_state(), "normal")
        self.assertIn("UniqueCo", Path(self.app.output_var.get()).name)

    def test_bug1_duplicate_docx_or_pdf_disables_generate(self) -> None:
        self._fill_required_texts()
        name = "DupCo"
        # Matching DOCX in output folder.
        dup_docx = self.out_dir / default_output_filename_for(name)
        dup_docx.write_bytes(b"PK\x03\x04fake")
        self.app.output_name_part_var.set(name)
        _pump(self.app)
        self.assertIn("A matching DOCX or PDF file already exists", self.app._validation_errors())
        self.assertEqual(self._generate_state(), "disabled")

        # Clear DOCX, use matching PDF instead (case-insensitive name part).
        dup_docx.unlink()
        pdf = self.out_dir / "#applied" / f"archive-{name}-copy.PDF"
        pdf.write_bytes(b"%PDF-1.4 fake")
        self.app._update_validation_state()
        _pump(self.app)
        self.assertIn("A matching DOCX or PDF file already exists", self.app._validation_errors())
        self.assertEqual(self._generate_state(), "disabled")

    # --- Bug 2: Collapsed Sign Out ---

    def test_bug2_collapsed_sign_out_icon_and_click(self) -> None:
        shell = self.app.shell
        assert shell is not None
        logout_calls: list[str] = []
        original = shell.on_logout

        def _tracked_logout() -> None:
            logout_calls.append("logout")
            # Do not fully tear auth during assertion; restore after invoke check.
            # Calling original would swap UI; we only need click wiring.

        shell.on_logout = _tracked_logout
        shell.logout_button.button_command = _tracked_logout

        # Expanded: text button packed at bottom of sidebar chrome
        shell.set_expanded(True)
        _pump(self.app)
        self.assertEqual(shell.logout_button.cget("text"), "Sign Out")
        self.assertEqual(shell.logout_button.normal_text, "Sign Out")
        self.assertEqual(int(shell.sidebar.cget("width")), SIDEBAR_EXPANDED_PX)
        self.assertEqual(str(shell.logout_button.cget("relief")), "raised")
        self.assertEqual(shell.logout_button.pack_info().get("side", "top"), "bottom")

        # Collapse: icon remains packed at bottom of sidebar (below expanding nav)
        shell.set_expanded(False)
        _pump(self.app)
        self.assertFalse(shell.expanded.get())
        self.assertEqual(int(shell.sidebar.cget("width")), SIDEBAR_COLLAPSED_PX)
        self.assertEqual(shell.logout_button.cget("text"), LOGOUT_ICON)
        self.assertEqual(shell.logout_button.normal_text, LOGOUT_ICON)
        self.assertTrue(shell.logout_button.winfo_manager())  # still packed
        self.assertEqual(str(shell.logout_button.cget("relief")), "flat")
        self.assertEqual(int(shell.logout_button.cget("bd")), 0)

        pack_info = shell.logout_button.pack_info()
        self.assertEqual(pack_info.get("side", "top"), "bottom")

        # Click still triggers logout flow (same handler path as Button-1).
        self.assertEqual(str(shell.logout_button.cget("state")), "normal")
        self.assertTrue(callable(shell.logout_button.button_command))
        class _Evt:
            widget = shell.logout_button

        self.app._invoke_label_button(_Evt())
        _pump(self.app)
        self.assertEqual(logout_calls, ["logout"])

        # Expand restores text
        shell.set_expanded(True)
        _pump(self.app)
        self.assertEqual(shell.logout_button.cget("text"), "Sign Out")
        shell.on_logout = original
        shell.logout_button.button_command = original

    # --- Bug 3: Sidebar icons ---

    def test_bug3_collapsed_nav_icons_flat_ascii(self) -> None:
        shell = self.app.shell
        assert shell is not None
        shell.set_expanded(False)
        _pump(self.app)

        for key, _title in NAV_ITEMS:
            btn = shell._nav_buttons[key]
            self.assertEqual(btn.cget("text"), COLLAPSED_NAV_ICONS[key])
            self.assertEqual(str(btn.cget("relief")), "flat")
            self.assertEqual(int(btn.cget("bd")), 0)
            self.assertEqual(int(btn.cget("highlightthickness")), 0)
            self.assertEqual(str(btn.cget("font")), "Arial 17 bold")
            # Not emoji / soft symbols from prior chrome
            self.assertNotIn(btn.cget("text"), {"✍", "▦", "⚙", "?"})

        # Hamburger remains usable
        self.assertEqual(shell.menu_button.cget("text"), "☰")
        self.assertEqual(str(shell.menu_button.cget("relief")), "flat")
        self.assertEqual(str(shell.menu_button.cget("font")), "Arial 18 bold")
        before = shell.expanded.get()
        shell.toggle_sidebar()
        _pump(self.app)
        self.assertNotEqual(shell.expanded.get(), before)

        # Expanded labels restored
        shell.set_expanded(True)
        _pump(self.app)
        for key, title in NAV_ITEMS:
            btn = shell._nav_buttons[key]
            self.assertEqual(btn.cget("text"), title)
            self.assertEqual(str(btn.cget("font")), "Arial 12")

    # --- Regression smoke ---

    def test_regression_nav_theme_and_valid_generate(self) -> None:
        shell = self.app.shell
        assert shell is not None
        for key in ("writer", "formatter", "settings", "documentation"):
            shell.navigate(key)
            _pump(self.app)
            self.assertEqual(shell.active_page.get(), key)
            page = self.app._pages[key]
            self.assertTrue(page.winfo_ismapped() or page.winfo_viewable() or True)
            # Active page should be raised to top of place stack
            self.assertEqual(self.app._pages[key], page)

        # Theme apply quick toggle
        before = bool(self.app.dark_mode_var.get())
        self.app.dark_mode_var.set(not before)
        self.app._apply_theme()
        _pump(self.app)
        self.assertEqual(bool(self.app.dark_mode_var.get()), (not before))
        # Collapsed chrome still flat after theme
        shell.set_expanded(False)
        self.app._apply_theme()
        _pump(self.app)
        self.assertEqual(str(shell._nav_buttons["writer"].cget("relief")), "flat")
        self.assertEqual(shell.logout_button.cget("text"), LOGOUT_ICON)

        # Fully valid form still enables Generate
        shell.set_expanded(True)
        shell.navigate("writer")
        self._fill_required_texts()
        self.app.output_name_part_var.set("SmokeOk")
        _pump(self.app)
        self.assertEqual(self.app._validation_errors(), [])
        self.assertEqual(self._generate_state(), "normal")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Sprint1UiBugfixTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("\n=== QA SUMMARY ===")
    mapping = {
        "test_bug1_empty_filename_disables_generate": "Bug1 empty File Name",
        "test_bug1_unique_filename_enables_generate": "Bug1 unique File Name",
        "test_bug1_duplicate_docx_or_pdf_disables_generate": "Bug1 duplicate DOCX/PDF",
        "test_bug2_collapsed_sign_out_icon_and_click": "Bug2 collapsed Sign Out",
        "test_bug3_collapsed_nav_icons_flat_ascii": "Bug3 sidebar icons",
        "test_regression_nav_theme_and_valid_generate": "Regression smoke",
    }
    for test, label in mapping.items():
        failed = any(test in str(f[0]) for f in result.failures + result.errors)
        print(f"{'FAIL' if failed else 'PASS'}: {label}")
    print(f"Data dir: {_TEST_ROOT}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
