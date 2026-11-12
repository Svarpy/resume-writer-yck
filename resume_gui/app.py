"""Main Tk window: wiring of the pages, the Writer page, and local generation through the client.

All data comes from the API through ``ResumeClient`` (cached on disk); documents are generated on this
machine by ``resume_client.engine``. This file holds no storage or business rules.
"""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Any, Optional

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from tkinter import filedialog, messagebox

from resume_client import ClientError, ResumeClient, engine, load_client_config
from resume_core.constants import APP_VERSION
from resume_core.render import count_words
from resume_core.settings import Settings, SettingsError
from resume_gui.auth_view import AuthView
from resume_gui.formatter_page import FormatterPage
from resume_gui.profile_page import ProfilePage
from resume_gui.scrolling import ScrollRouter
from resume_gui.settings_page import SettingsPage
from resume_gui.shell import PROFILE_KEY, AppShell
from resume_gui.toolkit import ThemedToolkit

# Settings keys whose change requires the Writer page to be rebuilt.
_WRITER_LAYOUT_PREFIXES = ("sections.", "fonts.", "appearance.editor_font_size")
_THEME_KEYS = ("appearance.dark_mode", "appearance.accent_color")
SETTINGS_SAVE_DELAY_MS = 400  # edits are sent to the server in one batch shortly after you stop typing
NO_FORMAT_NAME = "none yet (upload a template in the Formatter)"


class ResumeWriterApp(ThemedToolkit, tk.Tk):
    def __init__(self, client: Optional[ResumeClient] = None) -> None:
        super().__init__()
        self.title(f"Resume Writer {APP_VERSION}")
        self.geometry("1060x880")
        self.minsize(860, 700)

        self.client = client or ResumeClient(load_client_config())
        if not self.client.signed_in:
            self.client.restore_session()      # stay signed in until the user clicks Sign Out

        # Settings of the signed-in user for the default format (defaults until sign-in).
        self.settings = Settings()
        self._format_info: Optional[dict[str, Any]] = None
        self._format_id = ""
        self._has_format = False
        self._loading_settings = False
        self._education_guard = False
        self._pending_changes: dict[str, Any] = {}
        self._flush_job: Optional[str] = None
        self.settings.add_listener(self._on_settings_changed)

        self.dark_mode_var = tk.BooleanVar(value=bool(self.settings.get("appearance.dark_mode")))
        self.font_var = tk.StringVar(value="Arial")
        self.name_size_var = tk.StringVar(value="16")
        self.heading_size_var = tk.StringVar(value="12")
        self.body_size_var = tk.StringVar(value="11")
        self.output_name_part_var = tk.StringVar(value="")
        self.output_var = tk.StringVar(value="")
        self.output_warning_var = tk.StringVar(value="")
        self.validation_var = tk.StringVar(value="")

        # Writer text boxes and word-count labels, keyed by section key.
        self.section_texts: dict[str, tk.Text] = {}
        self.section_count_vars: dict[str, tk.StringVar] = {}

        self._widgets_by_role = {}
        self._submit_widgets = []
        self._suppress_output_path_refresh = False
        self._pages: dict[str, tk.Widget] = {}
        self.shell: Optional[AppShell] = None
        self.auth_view: Optional[AuthView] = None

        self._configure_style()
        self._build_menu()
        self._build_root_containers()
        self._bind_shortcuts()
        self._wire_validation()
        self._active_page = "writer"
        self._scroll_router = ScrollRouter(self, lambda: self._pages.get(self._active_page))

        if self.client.signed_in:
            self._enter_authenticated_shell(self.client.profile_data)
        else:
            self._show_auth()

    # ------------------------------------------------------------------
    # Settings (loaded from the client; edits are saved back in batches)
    # ------------------------------------------------------------------
    def current_format_name(self) -> str:
        return self._format_info["name"] if self._format_info else NO_FORMAT_NAME

    def _load_settings(self) -> None:
        """(Re)load the default format and its settings through the client (cached on disk)."""
        self.flush_settings()
        try:
            info = self.client.default_format()
            view = self.client.settings()
        except ClientError as exc:
            messagebox.showerror("Settings", str(exc))
            return
        self._format_info = info
        self._format_id = info["id"] if info else ""
        self._has_format = info is not None
        self._loading_settings = True
        try:
            self.settings.replace_all(view.settings())
        finally:
            self._loading_settings = False
        if info:
            self._apply_typography(info)
        self._apply_theme_from_settings()
        self._rebuild_writer()
        self.settings_page.refresh()

    def _apply_typography(self, info: dict[str, Any]) -> None:
        self.font_var.set(str(info["font_name"]))
        self.name_size_var.set(str(info["name_size"]))
        self.heading_size_var.set(str(info["heading_size"]))
        self.body_size_var.set(str(info["body_size"]))

    def _on_settings_changed(self, keys: tuple[str, ...]) -> None:
        """Queue the change for the server and apply its effects to the running UI."""
        if self._loading_settings:
            return
        for key in keys:
            self._pending_changes[key] = self.settings.get(key)
        if self._flush_job is not None:
            self.after_cancel(self._flush_job)
        self._flush_job = self.after(SETTINGS_SAVE_DELAY_MS, self.flush_settings)
        if any(key in _THEME_KEYS for key in keys):
            self._apply_theme_from_settings()
        if any(key.startswith(_WRITER_LAYOUT_PREFIXES) for key in keys):
            self._rebuild_writer()
        elif "education.entries" in keys and not self._education_guard and hasattr(self, "education_box"):
            self._populate_education_box()
        if hasattr(self, "settings_page"):
            self.settings_page.on_settings_changed(keys)
        self._refresh_output_path()
        self._update_validation_state()

    def flush_settings(self) -> None:
        """Send pending setting changes to the server now (also called automatically after a short pause)."""
        if self._flush_job is not None:
            try:
                self.after_cancel(self._flush_job)
            except tk.TclError:
                pass
            self._flush_job = None
        if not self._pending_changes or not self.client.signed_in:
            return
        changes, self._pending_changes = self._pending_changes, {}
        try:
            self.client.update_settings(changes, format_id=self._format_id)
        except ClientError as exc:
            self._pending_changes = {**changes, **self._pending_changes}  # keep them and try again later
            if hasattr(self, "settings_page"):
                self.settings_page.show_save_error(str(exc))
            return
        if hasattr(self, "settings_page"):
            self.settings_page.show_save_error("")

    def destroy(self) -> None:
        if self._flush_job is not None:  # do not leave a pending timer behind
            try:
                self.after_cancel(self._flush_job)
            except tk.TclError:
                pass
            self._flush_job = None
        super().destroy()

    def api_docs_url(self) -> str:
        return self.client.config.api_url.rstrip("/") + "/docs"

    def open_api_docs(self) -> None:
        """Open the server's interactive API documentation (Swagger UI) in the default browser."""
        if not webbrowser.open(self.api_docs_url()):
            messagebox.showinfo("API documentation", f"Open this address in your browser:\n{self.api_docs_url()}")

    # ------------------------------------------------------------------
    # Backup (Settings > Backup)
    # ------------------------------------------------------------------
    def backup_contents_text(self) -> str:
        """One line describing what a backup would contain for this account."""
        try:
            info = self.client.backup_info()
        except ClientError as exc:
            return f"Backup is unavailable: {exc}"
        parts = ", ".join(f"{c['name']} ({c['documents']})" for c in info["collections"])
        return f"Backup of the whole '{info['database']}' database: {parts}."

    def download_backup(self) -> None:
        downloads = Path.home() / "Downloads"
        folder = filedialog.askdirectory(
            title="Choose where to save the backup",
            initialdir=str(downloads if downloads.is_dir() else Path.home()),
        )
        if not folder:
            return
        try:
            path = self.client.download_backup(Path(folder))
        except (ClientError, OSError) as exc:
            messagebox.showerror("Backup", str(exc))
            return
        messagebox.showinfo("Backup saved", f"Saved to:\n{path}")

    def _apply_theme_from_settings(self) -> None:
        self.dark_mode_var.set(bool(self.settings.get("appearance.dark_mode")))
        self._configure_style()
        self._apply_theme()
        self._refresh_custom_controls()

    def _after_theme_applied(self) -> None:
        # Theme defaults overwrite dynamic status colours; restore them.
        self._update_validation_state()
        if self.shell is not None:
            self.shell._refresh_nav_styles()  # sidebar chrome depends on the expanded state
        if hasattr(self, "settings_page"):
            self.settings_page.restyle()

    # ------------------------------------------------------------------
    # Shell / pages
    # ------------------------------------------------------------------
    def _build_root_containers(self) -> None:
        self.auth_container = self._track(tk.Frame(self, bg=self.c("app_bg")), "app_frame")
        self.shell_container = self._track(tk.Frame(self, bg=self.c("app_bg")), "app_frame")

        self.auth_view = AuthView(
            self.auth_container,
            app=self,
            client=self.client,
            on_authenticated=self._enter_authenticated_shell,
        )
        self.auth_view.pack(fill=tk.BOTH, expand=True)

        self.shell = AppShell(
            self.shell_container,
            app=self,
            on_logout=self._logout,
            on_navigate=self._show_page,
        )
        self.shell.pack(fill=tk.BOTH, expand=True)

        self.writer_page = self._track(tk.Frame(self.shell.content, bg=self.c("app_bg")), "app_frame")
        self.formatter_page = FormatterPage(
            self.shell.content,
            app=self,
            on_primary_changed=self._apply_primary_format,
        )
        self.settings_page = SettingsPage(
            self.shell.content,
            app=self,
        )
        self.profile_page = ProfilePage(self.shell.content, app=self)

        self._pages = {
            "writer": self.writer_page,
            "formatter": self.formatter_page,
            "settings": self.settings_page,
            PROFILE_KEY: self.profile_page,
        }
        for page in self._pages.values():
            page.place(x=0, y=0, relwidth=1, relheight=1)

        self._build_writer_ui(self.writer_page)
        self._update_validation_state()

    def _show_auth(self) -> None:
        self.shell_container.pack_forget()
        self.auth_container.pack(fill=tk.BOTH, expand=True)
        if self.auth_view is not None:
            self.auth_view.clear_form(mode="signin", keep_credentials=True)
            self.auth_view.focus_username()

    def _enter_authenticated_shell(self, profile: dict) -> None:
        self._load_settings()
        if self.shell is not None:
            self.shell.set_signed_in_label(
                display_name=profile.get("display_name", ""), username=profile.get("username", "")
            )
            self.shell.apply_default_collapse_for_width(self.winfo_width() or 1060)
        self.auth_container.pack_forget()
        self.shell_container.pack(fill=tk.BOTH, expand=True)
        if self.shell is not None:
            self.shell.navigate("writer")

    def _logout(self) -> None:
        self.flush_settings()
        self.client.logout()
        self._show_auth()

    def _refresh_sidebar_user_label(self) -> None:
        if self.shell is None:
            return
        profile = self.client.profile_data
        self.shell.set_signed_in_label(
            display_name=profile.get("display_name", ""), username=profile.get("username", "")
        )

    def _show_page(self, page_key: str) -> None:
        page = self._pages.get(page_key)
        if page is None:
            return
        page.lift()
        self._active_page = page_key
        if page_key == "formatter":
            self.formatter_page.refresh()
        elif page_key == "settings":
            self.settings_page.refresh()
        elif page_key == PROFILE_KEY:
            self.profile_page.refresh()

    def _apply_primary_format(self, _info: Optional[dict]) -> None:
        """The default format changed (None when none is left): reload its settings, fonts and sections."""
        self._load_settings()


    def _rebuild_writer(self) -> None:
        """Rebuild the Writer page, keeping whatever has been typed into sections that still exist."""
        if not hasattr(self, "writer_page"):
            return
        kept = {key: text.get("1.0", tk.END).rstrip("\n") for key, text in self.section_texts.items()
                if self._widget_alive(text)}
        for child in self.writer_page.winfo_children():
            child.destroy()
        self.section_texts = {}
        self.section_count_vars = {}
        self._prune_tracked_widgets()
        self._build_writer_ui(self.writer_page)
        for key, value in kept.items():
            widget = self.section_texts.get(key)
            if widget is not None and value:
                widget.insert("1.0", value)
        self._update_validation_state()

    def _choice_values(self, setting_key: str, current: str) -> tuple[str, ...]:
        values = [str(item) for item in self.settings.get(setting_key)]
        if current and current not in values:
            values.append(current)
        return tuple(values)

    def _writer_rows(self) -> list[list[dict]]:
        """Group the Writer sections into display rows: two 'half' sections or one 'full'."""
        rows: list[list[dict]] = []
        pending: list[dict] = []
        for spec in self.settings.writer_sections():
            if spec["width"] == "full":
                if pending:
                    rows.append(pending)
                    pending = []
                rows.append([spec])
            else:
                pending.append(spec)
                if len(pending) == 2:
                    rows.append(pending)
                    pending = []
        if pending:
            rows.append(pending)
        return rows

    def _build_writer_ui(self, root) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        pad = self._track(tk.Frame(root, bg=self.c("app_bg"), padx=16, pady=16), "app_frame")
        pad.pack(fill=tk.BOTH, expand=True)
        pad.columnconfigure(0, weight=1)
        pad.rowconfigure(1, weight=1)

        if not self._has_format:
            notice = self._label(
                pad,
                "No resume format yet. Open the Formatter and upload a template resume (.docx with {{placeholders}}): "
                "the first one you upload becomes your default format.",
            )
            notice.configure(fg=self.c("error_fg"), wraplength=760, justify=tk.LEFT)
            notice.grid(row=4, column=0, sticky="w", pady=(0, 8))

        controls = self._section(pad, "Format Options")
        controls.grid(row=0, column=0, sticky="ew")
        for column in range(8):
            controls.columnconfigure(column, weight=1 if column in (1, 3, 5, 7) else 0)

        self._combo(controls, "Font", self.font_var, self._choice_values("fonts.font_choices", self.font_var.get()), 0, 0)
        self._combo(controls, "Name Size", self.name_size_var,
                    self._choice_values("fonts.name_size_choices", self.name_size_var.get()), 0, 2)
        self._combo(controls, "Heading Size", self.heading_size_var,
                    self._choice_values("fonts.heading_size_choices", self.heading_size_var.get()), 0, 4)
        self._combo(controls, "Text Size", self.body_size_var,
                    self._choice_values("fonts.body_size_choices", self.body_size_var.get()), 0, 6)

        text_area = self._track(tk.Frame(pad, bg=self.c("app_bg")), "app_frame")
        text_area.grid(row=1, column=0, sticky="nsew", pady=(12, 12))
        text_area.columnconfigure(0, weight=1)
        text_area.columnconfigure(1, weight=1)

        grid_row = 0
        for group in self._writer_rows():
            # Three grid rows per group: label, text box, word-count footer.
            text_area.rowconfigure(grid_row + 1, weight=1, minsize=72)
            for column, spec in enumerate(group):
                span = 2 if spec["width"] == "full" else 1
                self.section_texts[spec["key"]] = self._text_box(
                    text_area, spec["label"], grid_row, column, columnspan=span, height=6
                )
                if spec["min_words"] or spec["max_words"]:
                    variable = tk.StringVar(value="")
                    self.section_count_vars[spec["key"]] = variable
                    footer = self._label(text_area, "", muted=True)
                    footer.configure(textvariable=variable)
                    footer.grid(row=grid_row + 2, column=column, columnspan=span, sticky="w", pady=(0, 8))
            grid_row += 3
        if not self.section_texts:
            self._label(
                text_area,
                "No Writer sections are enabled. Add or show sections in Settings > Resume Sections.",
                muted=True,
            ).grid(row=0, column=0, columnspan=2, sticky="w")

        self.education_box = self._section(pad, "Education")
        self.education_box.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self._populate_education_box()

        output = self._section(pad, "Output")
        output.grid(row=3, column=0, sticky="ew")
        output.columnconfigure(1, weight=1)

        self._label(output, "File Path").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        output_path_frame = self._track(tk.Frame(output, bg=self.c("panel_bg")), "panel_frame")
        output_path_frame.grid(row=0, column=1, columnspan=3, sticky="w", pady=(0, 8))
        output_path_label = self._label(output_path_frame, "", muted=True)
        output_path_label.configure(textvariable=self.output_var)
        output_path_label.pack(side=tk.LEFT)
        self._button(output_path_frame, "Browse", self._choose_output).pack(side=tk.LEFT)
        self._label(output, "File Name").grid(row=1, column=0, sticky="w", padx=(0, 8))
        file_name_frame = self._track(tk.Frame(output, bg=self.c("panel_bg")), "panel_frame")
        file_name_frame.grid(row=1, column=1, sticky="w")
        self.file_name_entry = self._entry(file_name_frame, self.output_name_part_var, width=25)
        self.file_name_entry.pack(side=tk.LEFT)
        self.file_name_check_label = self._label(file_name_frame, "")
        self.file_name_check_label.configure(font=("Arial", 14, "bold"), fg=self.c("ok_fg"))
        self.file_name_check_label.pack(side=tk.LEFT)
        self.generate_button = self._button(output, "Generate DOCX", self._generate, accent=True)
        self.generate_button.grid(row=1, column=3)
        self._submit_widgets.append(self.generate_button)
        self.output_warning_label = self._label(output, "", muted=True)
        self.output_warning_label.configure(textvariable=self.output_warning_var)
        self.output_warning_label.grid(row=2, column=1, columnspan=3, sticky="w", pady=(6, 0))
        self._refresh_output_path()

    # -- Education choices on the Writer page ---------------------------------------------
    def _education_wanted(self) -> bool:
        return any(row["kind"] == "education" for row in self.settings.rendered_sections())

    def _populate_education_box(self) -> None:
        """One checkbox per education entry from Settings; ticking one includes it in the resume (none is fine)."""
        box = self.education_box
        for child in box.winfo_children():
            child.destroy()
        self._prune_tracked_widgets()
        if not self._education_wanted():
            box.grid_remove()
            return
        box.grid()
        entries = self.settings.get("education.entries")
        if not entries:
            self._label(box, "No education entries yet. Add them in Settings > Education.", muted=True).grid(
                row=0, column=0, sticky="w")
            return
        for index, entry in enumerate(entries):
            first_line = next((line.split("\t")[0].strip() for line in str(entry.get("text", "")).splitlines()
                               if line.strip()), "")
            title = (entry.get("label") or "").strip() or first_line or f"Education {index + 1}"
            variable = tk.BooleanVar(value=bool(entry.get("enabled", True)))

            def toggle(i=index, var=variable) -> None:
                var.set(not var.get())
                self._refresh_custom_controls()
                self._set_education_enabled(i, var.get())

            choice = self._choice_label(box, title, variable, toggle)
            choice.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 18), pady=2)
        self._refresh_custom_controls()

    def _set_education_enabled(self, index: int, enabled: bool) -> None:
        rows = [dict(row) for row in self.settings.get("education.entries")]
        if not 0 <= index < len(rows) or bool(rows[index].get("enabled")) == enabled:
            return
        rows[index]["enabled"] = enabled
        self._education_guard = True
        try:
            self.settings.set("education.entries", rows)
        finally:
            self._education_guard = False

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label="About Resume Writer", command=self._show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menu_bar)

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About Resume Writer",
            f"Resume Writer\n{APP_VERSION}",
        )

    def _bind_shortcuts(self) -> None:
        for sequence in (
            "<Command-Return>",
            "<Command-KeyPress-Return>",
            "<Control-Return>",
            "<Control-KeyPress-Return>",
            "<Command-KP_Enter>",
            "<Control-KP_Enter>",
        ):
            self.bind_class("SubmitShortcut", sequence, self._shortcut_generate)
            self.bind(sequence, self._shortcut_generate)

    def _wire_validation(self) -> None:
        self.output_name_part_var.trace_add("write", lambda *_args: self._update_validation_state())
        self.output_var.trace_add("write", lambda *_args: self._update_validation_state())
        self.output_name_part_var.trace_add("write", lambda *_args: self._refresh_output_path())

    def _shortcut_generate(self, _event) -> str:
        if self._is_form_valid():
            self._generate()
        return "break"

    def _text_value(self, text_widget: tk.Text) -> str:
        return text_widget.get("1.0", tk.END).strip()

    def _texts(self) -> dict[str, str]:
        return {key: self._text_value(widget) for key, widget in self.section_texts.items()
                if self._widget_alive(widget)}

    # ------------------------------------------------------------------
    # Validation and output path (rules live in resume_client.engine)
    # ------------------------------------------------------------------
    def _validation_errors(self) -> list[str]:
        errors = []
        if not self._has_format:
            errors.append("Upload a resume format in the Formatter first")
        errors += engine.validation_errors(
            self.settings, self._texts(), self.output_name_part_var.get(), self.client.username
        )
        return errors

    def _is_form_valid(self) -> bool:
        return not self._validation_errors()

    def _update_word_counts(self) -> None:
        for spec in self.settings.writer_sections():
            variable = self.section_count_vars.get(spec["key"])
            widget = self.section_texts.get(spec["key"])
            if variable is None or widget is None or not self._widget_alive(widget):
                continue
            words = count_words(self._text_value(widget))
            variable.set(f"{spec['label']}: {words} words (required: {engine.word_limit_text(spec)})")

    def _update_validation_state(self) -> None:
        if not hasattr(self, "generate_button") or not self._widget_alive(self.generate_button):
            return
        self._update_word_counts()
        errors = self._validation_errors()
        if errors:
            self.validation_var.set("Generate disabled: " + "; ".join(errors))
            submit_state = tk.DISABLED
        else:
            self.validation_var.set("Ready to generate.")
            submit_state = tk.NORMAL
        for widget in self._submit_widgets:
            if self._widget_alive(widget):
                widget.configure(state=submit_state)
        self._refresh_custom_controls()
        self._apply_button_state()
        self._style_status_labels()
        self._refresh_output_warning()

    def _style_status_labels(self) -> None:
        for widget in self._widgets_by_role.get("muted_label", []):
            if not self._widget_alive(widget):
                continue
            try:
                widget.configure(fg=self.c("muted_fg"))
            except tk.TclError:
                pass

    def _output_directory(self) -> Path:
        return engine.output_directory(self.settings)

    def _output_path(self) -> Path:
        return engine.output_path(self.settings, self.output_name_part_var.get(), self.client.username)

    def output_preview_text(self) -> str:
        """Path shown in Settings > Output (uses the Writer File Name field when filled)."""
        return str(self._output_path())

    def _refresh_output_path(self) -> None:
        if not hasattr(self, "output_var") or self._suppress_output_path_refresh:
            return
        new_path = str(self._output_path())
        if self.output_var.get() != new_path:
            self.output_var.set(new_path)

    def _matching_existing_output_files(self) -> list[Path]:
        return engine.duplicate_files(self.settings, self.output_name_part_var.get())

    def _refresh_output_warning(self) -> None:
        if not hasattr(self, "output_warning_var"):
            return
        matches = self._matching_existing_output_files()
        if matches:
            output_dir = self._output_directory()
            shown = ", ".join(
                str(path.relative_to(output_dir)) if path.is_relative_to(output_dir) else str(path)
                for path in matches[:3]
            )
            extra = "" if len(matches) <= 3 else f" and {len(matches) - 3} more"
            self.output_warning_var.set(f"Warning: matching file may already exist: {shown}{extra}")
        else:
            self.output_warning_var.set("")
        if hasattr(self, "output_warning_label"):
            try:
                self.output_warning_label.configure(fg=self.c("error_fg") if matches else self.c("muted_fg"))
            except tk.TclError:
                pass
        if hasattr(self, "file_name_check_label"):
            try:
                if not self.output_name_part_var.get().strip() or not self.settings.get("duplicate_check.enabled"):
                    self.file_name_check_label.configure(text="", fg=self.c("ok_fg"))
                elif matches:
                    self.file_name_check_label.configure(text="✕", fg=self.c("error_fg"))
                else:
                    self.file_name_check_label.configure(text="✓", fg=self.c("ok_fg"))
            except tk.TclError:
                pass

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose output folder",
            initialdir=str(self._output_directory()),
        )
        if selected:
            try:
                self.settings.set("output.directory", selected)  # saved + applied via the listener
            except SettingsError as exc:
                messagebox.showerror("Output folder", str(exc))

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Generate (on this machine)
    # ------------------------------------------------------------------
    def _generate(self) -> None:
        try:
            if not self._has_format or self._format_info is None:
                messagebox.showerror("Cannot generate resume", "Upload a resume format in the Formatter first.")
                return
            if not self._is_form_valid():
                messagebox.showerror("Cannot generate resume", self.validation_var.get())
                return
            ctx = engine.WriterContext(
                self.settings, self._format_info, self.client.sample_path(), self.client.username
            )
            typography = {
                "font_name": self.font_var.get(),
                "name_size": int(self.name_size_var.get()),
                "heading_size": int(self.heading_size_var.get()),
                "body_size": int(self.body_size_var.get()),
            }
            output_path = engine.generate(ctx, self._texts(), self.output_name_part_var.get(), typography)
        except (ClientError, ValueError) as exc:
            messagebox.showerror("Could not generate resume", str(exc))
            return
        if self.settings.get("writer.clear_after_generate"):
            self._clear_text_inputs()
        messagebox.showinfo("Resume generated", f"Saved to:\n{output_path}")

    def _clear_text_inputs(self) -> None:
        for text_widget in self.section_texts.values():
            text_widget.delete("1.0", tk.END)
        self._suppress_output_path_refresh = True
        try:
            self.output_name_part_var.set("")
        finally:
            self._suppress_output_path_refresh = False
        self._update_validation_state()
