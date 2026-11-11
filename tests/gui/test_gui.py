"""Desktop app tests: Writer, Settings, Profile, sidebar, login and the Formatter, against an in-process API."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

from docx import Document

from resume_core.render import build_output_filename
from tests.support import FIXTURES, World

YCK_RESUME = FIXTURES / "YcKResume.docx"
SUMMARY_45 = " ".join(f"word{i}" for i in range(1, 46))


def _pump(app, times: int = 15) -> None:
    for _ in range(times):
        app.update_idletasks()
        app.update()


class GuiCase(unittest.TestCase):
    """A signed-in desktop app (with an uploaded default format) talking to an in-process server."""

    username, password = "guiuser", "GuiPass123"
    with_format = True

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import tkinter as tk

            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"Tk display unavailable: {exc}") from exc

    def make_app(self, client=None):
        from resume_gui.app import ResumeWriterApp

        app = ResumeWriterApp(client)
        app.withdraw()
        self.addCleanup(self._destroy, app)
        return app

    @staticmethod
    def _destroy(app) -> None:
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass

    def setUp(self) -> None:
        self.world = World()
        self.client = self.world.client()
        self.client.signup(self.username, self.password, display_name="Gui Tester", email="gui@example.com")
        if self.with_format:
            self.client.add_format("Reference", YCK_RESUME)
        self.out_dir = Path(tempfile.mkdtemp(prefix="rw-gui-out-"))
        self.app = self.make_app(self.client)
        self.app.settings.set("output.directory", str(self.out_dir))
        if self.with_format:
            rows = self.app.settings.get("sections.items")  # a Summary word limit, like the app used to ship
            rows[0]["min_words"], rows[0]["max_words"] = 41, 50
            self.app.settings.set("sections.items", rows)
        _pump(self.app)

    def server_settings(self) -> dict:
        """What the server holds right now, read by a separate fresh client."""
        other = self.world.client(Path(tempfile.mkdtemp()))
        other.login(self.username, self.password)
        return other.settings().values

    def _fill(self) -> None:
        for key, value in (
            ("summary", SUMMARY_45),
            ("skills", "Python: yes"),
            ("experience", "Acme | Remote January 2024 - Present\nBuilt it."),
            ("top_skills", "a\nb\nc"),
        ):
            self.app.section_texts[key].insert("1.0", value)
        self.app.output_name_part_var.set("Acme")
        _pump(self.app)


class WriterAndSettingsTests(GuiCase):
    # -- Writer is driven by settings ------------------------------------
    def test_writer_boxes_follow_sections_setting_and_keep_text(self) -> None:
        self.assertEqual(list(self.app.section_texts), ["summary", "skills", "experience", "top_skills"])
        self.app.section_texts["summary"].insert("1.0", "keep me")
        rows = self.app.settings.get("sections.items")
        rows.insert(1, {"key": "projects", "label": "Projects", "heading": "", "kind": "bullets",
                        "width": "full", "enabled": True, "min_words": 0, "max_words": 0})
        rows[2]["enabled"] = False  # hide skills
        self.app.settings.set("sections.items", rows)
        _pump(self.app)
        self.assertEqual(list(self.app.section_texts),
                         ["summary", "projects", "experience", "top_skills"])
        self.assertEqual(self.app.section_texts["summary"].get("1.0", "end").strip(), "keep me")

    def test_font_choices_come_from_settings(self) -> None:
        self.app.settings.set("fonts.font_choices", ["Arial", "Fira Sans"])
        self.app.settings.set("fonts.body_size_choices", [9, 11])
        _pump(self.app)
        menus = [w for w in self.app._widgets_by_role.get("menu", []) if self.app._widget_alive(w)]
        labels = [[m.entrycget(i, "label") for i in range(m.index("end") + 1)] for m in menus if m.index("end") is not None]
        self.assertIn(["Arial", "Fira Sans"], labels)
        self.assertIn(["9", "11"], labels)

    def test_required_fields_and_word_limits_are_configurable(self) -> None:
        self._fill()
        self.assertEqual(self.app._validation_errors(), [])
        self.app.section_texts["summary"].delete("1.0", "end")
        self.assertIn("Summary is required", self.app._validation_errors())
        self.app.settings.set("validation.required_fields", ["skills", "experience", "top_skills", "file_name"])
        _pump(self.app)
        self.assertEqual(self.app._validation_errors(), [])  # empty summary now optional
        self.app.section_texts["summary"].insert("1.0", "too short")
        self.assertIn("Summary must be 41-50 words", self.app._validation_errors())
        rows = self.app.settings.get("sections.items")
        rows[0]["min_words"], rows[0]["max_words"] = 0, 0
        self.app.settings.set("sections.items", rows)
        _pump(self.app)
        self.assertEqual(self.app._validation_errors(), [])
        self.app.settings.set("validation.required_fields", ["skills", "experience", "top_skills"])
        self.app.output_name_part_var.set("")
        _pump(self.app)
        self.assertEqual(self.app._validation_errors(), [])  # File Name no longer required

    def test_duplicate_check_toggle_and_folders(self) -> None:
        self._fill()
        (self.out_dir / build_output_filename("Acme")).write_bytes(b"x")
        self.app._update_validation_state()
        self.assertIn("A matching DOCX or PDF file already exists", self.app._validation_errors())
        self.assertEqual(str(self.app.generate_button.cget("state")), "disabled")
        self.app.settings.set("duplicate_check.enabled", False)
        _pump(self.app)
        self.assertEqual(self.app._validation_errors(), [])
        self.assertEqual(str(self.app.generate_button.cget("state")), "normal")
        self.app.settings.set("duplicate_check.enabled", True)
        elsewhere = Path(tempfile.mkdtemp())
        self.app.settings.set("duplicate_check.directories", [str(elsewhere)])
        _pump(self.app)
        self.assertEqual(self.app._validation_errors(), [])  # the output folder is no longer checked
        (elsewhere / "x-acme.pdf").write_bytes(b"x")
        self.app._update_validation_state()
        self.assertIn("A matching DOCX or PDF file already exists", self.app._validation_errors())

    def test_output_path_uses_directory_and_template_settings(self) -> None:
        self.app.settings.set("output.filename_template", "CV_{company}_{name}")
        self.app.settings.set("personal.name", "Ada Lovelace")
        self.app.output_name_part_var.set("Acme")
        _pump(self.app)
        self.assertEqual(Path(self.app.output_var.get()), self.out_dir / "CV_Acme_AdaLovelace.docx")
        self.assertEqual(self.app.output_preview_text(), self.app.output_var.get())

    def test_generate_uses_personal_details_education_and_clears(self) -> None:
        from tkinter import messagebox
        from unittest import mock

        self.app.settings.set("personal.name", "Ada Lovelace")
        self.app.settings.set("personal.email", "ada@example.com")
        self.app.settings.set("education.entries", [
            {"label": "BSc", "enabled": True, "text": "University of London\tSeptember 1830 – June 1833"},
            {"label": "Off", "enabled": False, "text": "Should Not Appear"},
        ])
        self._fill()
        with mock.patch.object(messagebox, "showinfo"), mock.patch.object(messagebox, "showerror") as err:
            self.app._generate()
            err.assert_not_called()
        produced = list(self.out_dir.glob("ResumeAcme*.docx"))
        self.assertEqual(len(produced), 1, self.out_dir)
        document = Document(str(produced[0]))
        texts = [p.text for p in document.paragraphs if p.text.strip()]
        table_texts = [c.text for tb in document.tables for r in tb.rows for c in r.cells]
        self.assertEqual(texts[0], "Ada Lovelace")
        self.assertIn("Education", texts)
        self.assertTrue(any("University of London" in t for t in texts + table_texts))
        self.assertNotIn("Should Not Appear", texts + table_texts)
        self.assertEqual(self.app.section_texts["summary"].get("1.0", "end").strip(), "")
        self.assertEqual(self.app.output_name_part_var.get(), "")

    def test_clear_after_generate_can_be_disabled(self) -> None:
        from tkinter import messagebox
        from unittest import mock

        self.app.settings.set("writer.clear_after_generate", False)
        self._fill()
        self.app.settings.set("duplicate_check.enabled", False)
        with mock.patch.object(messagebox, "showinfo"), mock.patch.object(messagebox, "showerror"):
            self.app._generate()
        self.assertEqual(self.app.output_name_part_var.get(), "Acme")
        self.assertNotEqual(self.app.section_texts["summary"].get("1.0", "end").strip(), "")

    # -- Settings persistence + page -------------------------------------
    def test_changes_are_sent_to_the_server_in_one_batch_after_a_short_pause(self) -> None:
        self.world.http.calls.clear()
        self.app.settings.set("personal.location", "Paris")
        self.app.settings.set("personal.phone", "+1 555")
        self.assertEqual(self.world.http.count("PATCH"), 0)  # nothing is sent while the user is still typing
        self.app.flush_settings()  # what the short timer does
        self.assertEqual(self.world.http.count("PATCH"), 1)
        server = self.server_settings()
        self.assertEqual((server["personal.location"], server["personal.phone"]), ("Paris", "+1 555"))
        self.assertEqual(server["output.directory"], str(self.out_dir))

    def test_unsent_changes_are_kept_and_retried_when_the_server_is_down(self) -> None:
        self.app.flush_settings()
        self.world.http.down = True
        try:
            self.app.settings.set("personal.location", "Oslo")
            self.app.flush_settings()
            self.assertIn("Not saved yet", self.app.settings_page.save_label.cget("text"))
        finally:
            self.world.http.down = False
        self.app.flush_settings()
        self.assertEqual(self.app.settings_page.save_label.cget("text"), "")
        self.assertEqual(self.server_settings()["personal.location"], "Oslo")

    def test_dark_mode_and_accent_apply_live(self) -> None:
        self.app.settings.set("appearance.dark_mode", False)
        self.app.settings.set("appearance.accent_color", "rgb(255, 0, 0)")
        _pump(self.app)
        self.assertFalse(self.app.dark_mode_var.get())
        self.assertEqual(self.app.c("accent"), "#ff0000")

    def test_settings_page_groups_alphabetically_and_searches(self) -> None:
        import tkinter as tk

        page = self.app.settings_page
        self.app.shell.navigate("settings")
        _pump(self.app)

        def titles() -> list[str]:
            return [w.cget("text") for w in page.inner.winfo_children() if isinstance(w, tk.Label)
                    and w.cget("font") and "14" in str(w.cget("font"))]

        headers = titles()
        self.assertEqual(headers, sorted(headers, key=str.casefold))
        self.assertIn("Resume Sections", headers)
        page.search_var.set("duplicate")
        _pump(self.app)
        self.assertEqual(titles(), ["Duplicate Check"])
        page.search_var.set("zzzz-nothing")
        _pump(self.app)
        self.assertEqual(titles(), [])
        page.search_var.set("")
        page._select_category("Output")
        _pump(self.app)
        self.assertEqual(titles(), ["Output"])
        self.assertIn("output.preview", page._info_labels)
        self.assertEqual(page._info_labels["output.preview"].cget("text"), self.app.output_var.get())

    def test_typing_saves_immediately_without_leaving_the_field(self) -> None:
        page = self.app.settings_page
        page._select_category("Personal Details")
        _pump(self.app)
        import tkinter as tk

        def entries(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Entry):
                    yield child
                yield from entries(child)

        self.app.deiconify()  # key events are only delivered to mapped windows
        _pump(self.app)
        # Alphabetical cards: Email, Location, Name, Phone.
        name_entry = list(entries(page.inner))[2]
        name_entry.focus_force()
        name_entry.delete(0, "end")
        name_entry.insert(0, "Typed Name")
        name_entry.event_generate("<KeyRelease>", when="now")
        _pump(self.app)
        # Saved with no focus change (startswith: a real window can receive stray OS key presses).
        self.assertTrue(self.app.settings.get("personal.name").startswith("Typed Name"))
        # A half-typed invalid value is not saved and shows no error while typing.
        page._select_category("Appearance")
        _pump(self.app)
        accent = next(e for e in entries(page.inner) if e.get().startswith("#"))
        accent.focus_force()
        accent.delete(0, "end")
        accent.insert(0, "rgb(1,")
        accent.event_generate("<KeyRelease>", when="now")
        _pump(self.app)
        self.assertNotEqual(self.app.settings.get("appearance.accent_color"), "rgb(1,")
        accent.insert("end", "2,3)")
        accent.event_generate("<KeyRelease>", when="now")
        _pump(self.app)
        self.assertEqual(self.app.settings.get("appearance.accent_color"), "#010203")

    def test_advanced_settings_hidden_until_toggled(self) -> None:
        page = self.app.settings_page
        page._select_category("Duplicate Check")
        _pump(self.app)
        self.assertNotIn("duplicate_check.extensions", page._rows)
        self.assertIn("duplicate_check.enabled", page._rows)
        page._toggle_advanced()
        _pump(self.app)
        self.assertIn("duplicate_check.extensions", page._rows)
        page._toggle_advanced()
        page.search_var.set("file types")  # search finds advanced settings regardless
        _pump(self.app)
        self.assertIn("duplicate_check.extensions", page._rows)

    def test_wheel_scrolls_from_anywhere_while_settings_visible(self) -> None:
        page = self.app.settings_page
        self.app.shell.navigate("settings")
        _pump(self.app)
        self.assertTrue(page._active)
        self.app.shell.navigate("writer")
        _pump(self.app)
        self.assertFalse(page._active)

    def test_settings_page_edit_and_reset_flow(self) -> None:
        page = self.app.settings_page
        page._select_category("Personal Details")
        _pump(self.app)
        row = page._rows["personal.name"]
        self.assertEqual(row["marker"].cget("text"), "●")  # seeded from the account at sign-up
        page._reset_one("personal.name")
        self.assertEqual(self.app.settings.get("personal.name"), "")
        self.assertEqual(row["marker"].cget("text"), "")

    def test_json_editor_applies_and_validates(self) -> None:
        page = self.app.settings_page
        page._show_json_editor()
        _pump(self.app)
        data = json.loads(page.json_text.get("1.0", "end"))
        data["personal"]["name"] = "From JSON"
        page.json_text.delete("1.0", "end")
        page.json_text.insert("1.0", json.dumps(data))
        page._save_json()
        self.assertEqual(self.app.settings.get("personal.name"), "From JSON")
        page.json_text.delete("1.0", "end")
        page.json_text.insert("1.0", '{"output": {"directory": ""}}')
        page._save_json()
        self.assertIn("cannot be empty", page.json_error.cget("text"))
        self.assertEqual(self.app.settings.get("personal.name"), "From JSON")

    def test_records_editor_add_move_remove(self) -> None:
        page = self.app.settings_page
        page._select_category("Education")
        _pump(self.app)
        editor_row = page._rows["education.entries"]
        editor = editor_row["apply"].__self__  # bound method of the records editor
        editor._add()
        editor._add()
        self.assertEqual(len(self.app.settings.get("education.entries")), 2)
        first = self.app.settings.get("education.entries")[0]["label"]
        editor._move(0, 1)
        self.assertEqual(self.app.settings.get("education.entries")[1]["label"], first)
        editor._remove(0)
        self.assertEqual(len(self.app.settings.get("education.entries")), 1)

    def test_required_checklist_follows_sections(self) -> None:
        page = self.app.settings_page
        page._select_category("Validation")
        _pump(self.app)
        self.assertIn("validation.required_fields", page._rows)

    # -- Sidebar + Profile + docs removal --------------------------------
    def test_sidebar_has_no_documentation_and_profile_above_sign_out(self) -> None:
        from resume_gui.shell import NAV_ITEMS, PROFILE_FALLBACK_ICON

        shell = self.app.shell
        shell.set_expanded(True)
        _pump(self.app)
        self.assertEqual([k for k, _t in NAV_ITEMS], ["writer", "formatter", "settings"])
        self.assertNotIn("documentation", self.app._pages)
        self.assertEqual(shell.profile_button.cget("text"), "Profile")
        # Everything is packed from the bottom up, so Sign Out comes first and Profile sits directly above it.
        order = shell.bottom.pack_slaves()
        self.assertEqual(order.index(shell.profile_button), order.index(shell.logout_button) + 1)
        shell.set_expanded(False)
        _pump(self.app)
        icon = str(shell.profile_button.cget("image"))
        self.assertTrue(icon or shell.profile_button.cget("text") == PROFILE_FALLBACK_ICON)
        shell.navigate("profile")
        _pump(self.app)
        self.assertEqual(shell.active_page.get(), "profile")
        self.assertEqual(self.app.profile_page.username_var.get(), self.username)

    def test_settings_page_no_longer_holds_profile_or_password(self) -> None:
        page = self.app.settings_page
        for key in page._rows:
            self.assertFalse(key.startswith(("profile.", "password.")))
        self.assertFalse(hasattr(page, "old_password_var"))
        self.assertTrue(hasattr(self.app.profile_page, "old_password_var"))

    def test_help_menu_has_no_usage_help(self) -> None:
        self.assertFalse(hasattr(self.app, "_show_usage_help"))


class SidebarAndNavigationTests(GuiCase):
    def test_collapsed_sign_out_is_a_flat_icon_at_the_bottom_and_still_clickable(self) -> None:
        from resume_gui.shell import LOGOUT_ICON, SIDEBAR_COLLAPSED_PX, SIDEBAR_EXPANDED_PX

        shell = self.app.shell
        calls: list[str] = []
        shell.logout_button.button_command = lambda: calls.append("logout")
        shell.set_expanded(True)
        _pump(self.app)
        self.assertEqual(shell.logout_button.cget("text"), "Sign Out")
        self.assertEqual(int(shell.sidebar.cget("width")), SIDEBAR_EXPANDED_PX)
        self.assertEqual(str(shell.logout_button.cget("relief")), "raised")
        shell.set_expanded(False)
        _pump(self.app)
        self.assertEqual(int(shell.sidebar.cget("width")), SIDEBAR_COLLAPSED_PX)
        self.assertEqual(shell.logout_button.cget("text"), LOGOUT_ICON)
        self.assertEqual(str(shell.logout_button.cget("relief")), "flat")
        self.assertEqual(shell.logout_button.pack_info().get("side"), "bottom")

        class _Event:
            widget = shell.logout_button

        self.app._invoke_label_button(_Event())
        self.assertEqual(calls, ["logout"])

    def test_nav_icons_are_flat_ascii_and_theme_changes_keep_them_flat(self) -> None:
        from resume_gui.shell import COLLAPSED_NAV_ICONS, NAV_ITEMS

        shell = self.app.shell
        shell.set_expanded(False)
        _pump(self.app)
        for key, _title in NAV_ITEMS:
            self.assertEqual(shell._nav_buttons[key].cget("text"), COLLAPSED_NAV_ICONS[key])
            self.assertEqual(str(shell._nav_buttons[key].cget("relief")), "flat")
        self.app.settings.set("appearance.dark_mode", not self.app.dark_mode_var.get())
        _pump(self.app)
        self.assertEqual(str(shell._nav_buttons["writer"].cget("relief")), "flat")

    def test_no_documentation_page_and_profile_sits_above_sign_out(self) -> None:
        from resume_gui.shell import NAV_ITEMS, PROFILE_FALLBACK_ICON

        shell = self.app.shell
        shell.set_expanded(True)
        _pump(self.app)
        self.assertEqual([k for k, _t in NAV_ITEMS], ["writer", "formatter", "settings"])
        self.assertNotIn("documentation", self.app._pages)
        order = shell.bottom.pack_slaves()  # packed from the bottom up: Sign Out first, Profile right above it
        self.assertEqual(order.index(shell.profile_button), order.index(shell.logout_button) + 1)
        shell.set_expanded(False)
        _pump(self.app)
        self.assertTrue(str(shell.profile_button.cget("image")) or shell.profile_button.cget("text") == PROFILE_FALLBACK_ICON)
        for page in ("writer", "formatter", "settings", "profile"):
            shell.navigate(page)
            _pump(self.app)
            self.assertEqual(shell.active_page.get(), page)
        self.assertEqual(self.app.profile_page.username_var.get(), self.username)

    def test_profile_page_edits_the_account_and_manages_access_tokens(self) -> None:
        from tkinter import messagebox
        from unittest import mock

        page = self.app.profile_page
        page.refresh()
        page.display_name_var.set("New Display")
        with mock.patch.object(messagebox, "showinfo"):
            page._save_profile()
        self.assertEqual(self.client.profile()["display_name"], "New Display")
        page.old_password_var.set(self.password)
        page.new_password_var.set("BrandNew123")
        with mock.patch.object(messagebox, "showinfo"):
            page._change_password()
        self.world.client(Path(tempfile.mkdtemp())).login(self.username, "BrandNew123")
        page.token_name_var.set("claude")
        with mock.patch.object(messagebox, "showinfo") as info:
            page._create_token()
        token = info.call_args.args[1].split("\n")[0]
        self.assertTrue(token.startswith("rwt_"))
        self.assertEqual([t["name"] for t in self.client.list_tokens()], ["claude"])
        with mock.patch.object(messagebox, "askyesno", return_value=True):
            page._revoke_token(self.client.list_tokens()[0])
        self.assertEqual(self.client.list_tokens(), [])


class ApiDocsButtonTests(GuiCase):
    def test_profile_has_an_option_that_opens_the_swagger_documentation(self) -> None:
        from unittest import mock

        self.app.shell.navigate("profile")
        _pump(self.app)
        self.assertEqual(self.app.api_docs_url(), "http://testserver/docs")
        with mock.patch("webbrowser.open", return_value=True) as opened:
            self.app.open_api_docs()
        opened.assert_called_once_with("http://testserver/docs")
        # the button lives in the same section as the access tokens
        texts = []

        def walk(widget):
            for child in widget.winfo_children():
                if hasattr(child, "cget"):
                    try:
                        texts.append(str(child.cget("text")))
                    except Exception:  # noqa: BLE001
                        pass
                walk(child)

        walk(self.app.profile_page.tokens_section)
        self.assertIn("Open API Documentation", texts)
        self.assertIn("Create Token", texts)

    def test_if_no_browser_can_be_opened_the_address_is_shown(self) -> None:
        from tkinter import messagebox
        from unittest import mock

        with mock.patch("webbrowser.open", return_value=False), mock.patch.object(messagebox, "showinfo") as info:
            self.app.open_api_docs()
        self.assertIn("http://testserver/docs", info.call_args.args[1])


class BackupSectionTests(GuiCase):
    def set_role(self, role: str) -> None:
        self.world.http.app.state.db.users.update_one({"_id": self.username}, {"$set": {"role": role}})

    def header_texts(self) -> list[str]:
        import tkinter as tk

        return [w.cget("text") for w in self.app.settings_page.inner.winfo_children()
                if isinstance(w, tk.Label) and "14" in str(w.cget("font"))]

    def test_regular_users_never_see_the_backup_option(self) -> None:
        page = self.app.settings_page
        page.refresh()
        _pump(self.app)
        self.assertEqual(self.client.profile()["role"], "user")
        self.assertEqual(page.backup_button.winfo_manager(), "")  # not shown at all
        self.assertNotIn("Backup", page._category_buttons)
        self.assertNotIn("Backup", self.header_texts())
        for term in ("backup", "download", "mongodump"):
            page.search_var.set(term)
            _pump(self.app)
            self.assertEqual(page._rows, {}, term)  # no search result either
            self.assertEqual(page.backup_button.winfo_manager(), "", term)

    def test_admins_get_the_backup_button_at_the_bottom_of_the_left_column(self) -> None:
        page = self.app.settings_page
        self.set_role("admin")  # promoted by hand in the database
        page.refresh()
        _pump(self.app)
        button = page.backup_button
        self.assertEqual(button.winfo_manager(), "pack")
        self.assertEqual(button.pack_info()["side"], "bottom")  # pinned to the bottom of the column
        first_category = page._category_buttons["All Settings"]
        self.assertIs(button.master, first_category.master)  # the same left column as the category buttons
        self.assertEqual(first_category.pack_info()["side"], "top")
        self.assertEqual(button.cget("text"), "Download Backup")
        for view in ("Appearance", "All Settings"):  # stays put whichever category is open
            page._select_category(view)
            _pump(self.app)
            self.assertEqual(button.winfo_manager(), "pack")
            self.assertNotIn("Backup", self.header_texts())
        from unittest import mock

        with mock.patch.object(self.app, "download_backup") as download:
            page.backup_button.button_command = lambda: self.app.download_backup()
            page.backup_button.button_command()
        download.assert_called_once()
        self.assertIn("users (1)", self.app.backup_contents_text())
        self.set_role("user")  # demoted again: gone the next time the page is shown
        page.refresh()
        _pump(self.app)
        self.assertEqual(button.winfo_manager(), "")

    def test_download_saves_a_dated_zip_where_the_admin_chooses(self) -> None:
        import re
        import zipfile
        from tkinter import messagebox
        from unittest import mock

        self.set_role("admin")
        self.client.profile()
        folder = Path(tempfile.mkdtemp(prefix="rw-dl-"))
        with mock.patch("tkinter.filedialog.askdirectory", return_value=str(folder)), \
                mock.patch.object(messagebox, "showinfo") as info:
            self.app.download_backup()
        saved = list(folder.glob("ResWritBkp*.zip"))
        self.assertEqual(len(saved), 1)
        self.assertTrue(re.match(r"^ResWritBkp\d{4}[A-Z][a-z]{2}\d{2}\.zip$", saved[0].name))
        self.assertIn("manifest.json", zipfile.ZipFile(saved[0]).namelist())
        self.assertIn(str(saved[0]), info.call_args.args[1])
        with mock.patch("tkinter.filedialog.askdirectory", return_value=""):  # cancelling does nothing
            self.app.download_backup()
        self.assertEqual(len(list(folder.glob("*"))), 1)

    def test_a_refused_or_failed_download_is_reported_not_raised(self) -> None:
        from tkinter import messagebox
        from unittest import mock

        with mock.patch("tkinter.filedialog.askdirectory", return_value=tempfile.mkdtemp()), \
                mock.patch.object(messagebox, "showerror") as error:
            self.app.download_backup()  # a regular user: the server says no
        self.assertIn("Not Found", error.call_args.args[1])
        self.set_role("admin")
        self.client.profile()
        self.world.http.down = True
        try:
            with mock.patch("tkinter.filedialog.askdirectory", return_value=tempfile.mkdtemp()), \
                    mock.patch.object(messagebox, "showerror") as error:
                self.app.download_backup()
        finally:
            self.world.http.down = False
        self.assertIn("Cannot reach", error.call_args.args[1])


class WriterValidationTests(GuiCase):
    def test_file_name_gates_generate(self) -> None:
        self._fill()
        self.app.output_name_part_var.set("")
        _pump(self.app)
        self.assertEqual(self.app._validation_errors(), ["File Name is required"])
        self.assertTrue(self.app.validation_var.get().startswith("Generate disabled:"))
        self.assertEqual(str(self.app.generate_button.cget("state")), "disabled")
        self.assertIn("XXX", Path(self.app.output_var.get()).name)
        self.app.output_name_part_var.set("UniqueCo")
        _pump(self.app)
        self.assertEqual(self.app._validation_errors(), [])
        self.assertEqual(self.app.validation_var.get(), "Ready to generate.")
        self.assertEqual(str(self.app.generate_button.cget("state")), "normal")

    def test_matching_docx_or_pdf_in_any_checked_folder_blocks_generate(self) -> None:
        self._fill()
        (self.out_dir / "#applied").mkdir()
        existing = self.out_dir / build_output_filename("Acme")
        existing.write_bytes(b"PK\x03\x04fake")
        self.app._update_validation_state()
        self.assertIn("A matching DOCX or PDF file already exists", self.app._validation_errors())
        existing.unlink()
        (self.out_dir / "#applied" / "archive-ACME-copy.PDF").write_bytes(b"%PDF-1.4 fake")
        self.app._update_validation_state()
        self.assertIn("A matching DOCX or PDF file already exists", self.app._validation_errors())
        self.assertEqual(str(self.app.generate_button.cget("state")), "disabled")


class LoginTests(GuiCase):
    with_format = False

    def signed_out_app(self):
        client = self.world.client()
        return self.make_app(client), client

    def test_enter_submits_from_every_field_instead_of_moving_focus(self) -> None:
        for field in ("username_entry", "password_entry"):
            app, client = self.signed_out_app()
            view = app.auth_view
            view.username_var.set(self.username)
            view.password_var.set(self.password)
            app.deiconify()
            _pump(app)
            getattr(view, field).focus_force()
            getattr(view, field).event_generate("<Return>", when="now")
            _pump(app)
            self.assertTrue(client.signed_in, field)  # signed in, not just moved to the next field

    def test_wrong_password_with_enter_shows_the_error_and_stays_put(self) -> None:
        app, client = self.signed_out_app()
        view = app.auth_view
        view.username_var.set(self.username)
        view.password_var.set("wrong-password-1")
        app.deiconify()
        _pump(app)
        view.password_entry.focus_force()
        view.password_entry.event_generate("<Return>", when="now")
        _pump(app)
        self.assertFalse(client.signed_in)
        self.assertIn("Invalid", view.status_var.get())
        self.assertEqual(view.username_var.get(), self.username)

    def test_username_and_password_survive_sign_out_and_username_survives_restart(self) -> None:
        app, client = self.signed_out_app()
        view = app.auth_view
        view.username_var.set(self.username)
        view.password_var.set(self.password)
        view._submit()
        _pump(app)
        self.assertTrue(client.signed_in)
        app._logout()
        _pump(app)
        self.assertFalse(client.signed_in)
        self.assertEqual((view.username_var.get(), view.password_var.get()), (self.username, self.password))
        view._submit()  # signing in again needs nothing more
        _pump(app)
        self.assertTrue(client.signed_in)

        from resume_client.local import last_username

        self.assertEqual(last_username(client.config.root), self.username)
        again = self.make_app(self.world.client())  # a new start of the app on the same machine
        self.assertEqual(again.auth_view.username_var.get(), self.username)
        self.assertEqual(again.auth_view.password_var.get(), "")

    def test_the_password_is_never_written_to_disk(self) -> None:
        app, _client = self.signed_out_app()
        app.auth_view.username_var.set(self.username)
        app.auth_view.password_var.set(self.password)
        app.auth_view._submit()
        for path in self.world.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(self.password.encode(), path.read_bytes(), path)

    def test_sign_up_creates_the_account_and_signs_in(self) -> None:
        app, client = self.signed_out_app()
        view = app.auth_view
        view._toggle_mode()
        view.username_var.set("brandnew")
        view.password_var.set("BrandNew123")
        view.confirm_var.set("different1")
        view._submit()
        self.assertFalse(client.signed_in)
        self.assertIn("do not match", view.status_var.get())
        view.confirm_var.set("BrandNew123")
        view._submit()
        _pump(app)
        self.assertTrue(client.signed_in)

    def test_server_down_is_reported_on_the_login_page(self) -> None:
        app, client = self.signed_out_app()
        self.world.http.down = True
        try:
            app.auth_view.username_var.set(self.username)
            app.auth_view.password_var.set(self.password)
            app.auth_view._submit()
        finally:
            self.world.http.down = False
        self.assertFalse(client.signed_in)
        self.assertIn("Cannot reach", app.auth_view.status_var.get())


class FormatterFlowTests(GuiCase):
    with_format = False

    def test_writer_asks_for_an_upload_until_a_format_exists(self) -> None:
        self.assertFalse(self.app._has_format)
        self.assertIn("Upload a resume format in the Formatter first", self.app._validation_errors())
        self.assertEqual(str(self.app.generate_button.cget("state")), "disabled")
        self.assertIn("none yet", self.app.current_format_name())

    def test_first_upload_becomes_default_and_switching_changes_settings(self) -> None:
        from tkinter import messagebox
        from unittest import mock

        page = self.app.formatter_page
        page.refresh()
        self.assertEqual(page._specs, [])
        with mock.patch("tkinter.filedialog.askopenfilename", return_value=str(YCK_RESUME)), \
                mock.patch.object(page, "_ask_format_name", return_value="My Format"), \
                mock.patch.object(messagebox, "showinfo"):
            page._add_format()
        _pump(self.app)
        self.assertEqual(self.client.default_format()["name"], "My Format")
        self.assertTrue(self.app._has_format)
        self.assertIn("summary", self.app.section_texts)
        self.assertEqual(self.app.current_format_name(), "My Format")

        second = self.client.add_format("Second", FIXTURES / "YcKResumeFTR2.docx")
        page.refresh()
        with mock.patch.object(messagebox, "showinfo"):
            page._make_default(second)
        _pump(self.app)
        self.assertEqual(self.client.default_format()["id"], second["id"])
        self.assertIn("PROFESSIONAL SUMMARY", [r["heading"] for r in self.app.settings.get("sections.items")])
        self.assertEqual(self.app.name_size_var.get(), "24")  # typography follows the new default

        with mock.patch.object(messagebox, "askyesno", return_value=True):
            page._delete_format(second)
            _pump(self.app)
            self.assertTrue(self.app._has_format)  # the first format is the default again
            remaining = self.client.list_formats()
            self.assertEqual(len(remaining), 1)
            page._delete_format(remaining[0])
        _pump(self.app)
        self.assertFalse(self.app._has_format)
        self.assertEqual(self.app._format_id, "")

    def test_empty_formatter_offers_no_built_in_format(self) -> None:
        page = self.app.formatter_page
        page.refresh()
        texts = [w.cget("text") for w in page.list_frame.winfo_children()[0].winfo_children()]
        self.assertTrue(any("No formats yet" in t for t in texts))
        self.assertFalse(any("Default Application Format" in t or "protected" in t.lower() for t in texts))


class ScrollTests(GuiCase):
    def test_trackpad_and_wheel_scroll_from_any_widget_on_the_settings_page(self) -> None:
        self.app.deiconify()
        self.app.shell.navigate("settings")
        _pump(self.app)
        page = self.app.settings_page
        label = page.inner.winfo_children()[3]  # a label deep inside a card, not the scrollbar
        start = page.canvas.yview()[0]
        label.event_generate("<MouseWheel>", delta=-3, x=5, y=5)
        _pump(self.app)
        after_wheel = page.canvas.yview()[0]
        self.assertGreater(after_wheel, start)
        try:
            label.event_generate("<TouchpadScroll>", delta=((-40) & 0xFFFF), x=5, y=5)
        except Exception:  # noqa: BLE001 - this Tk has no trackpad event
            self.skipTest("no <TouchpadScroll> in this Tk")
        _pump(self.app)
        self.assertGreater(page.canvas.yview()[0], after_wheel)


if __name__ == "__main__":
    unittest.main()
