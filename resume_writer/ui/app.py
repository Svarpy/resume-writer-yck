"""Main Tk application shell and Writer page."""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Optional

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from tkinter import filedialog, messagebox

from formats_store import DEFAULT_FORMAT_VALUES
import user_auth
from user_auth import get_current_user

from resume_writer.constants import (
    APP_VERSION,
    AUTHOR_NAME,
    BODY_SIZE_CHOICES,
    DEFAULT_BACHELORS_EDUCATION,
    DEFAULT_MASTERS_EDUCATION,
    DEFAULT_OUTPUT_DIR,
    EMAIL,
    FONT_CHOICES,
    HEADING_SIZE_CHOICES,
    LOCATION,
    NAME_SIZE_CHOICES,
    PHONE,
    THEMES,
)
from resume_writer.docs.loader import load_how_to_use_section
from resume_writer.render.api import build_resume
from resume_writer.render.models import ResumeContent, resume_format_from_store
from resume_writer.render.parse import (
    count_words,
    default_output_filename_for,
    find_matching_output_files,
)
from resume_writer.ui.auth import AuthView
from resume_writer.ui.documentation import DocumentationPage
from resume_writer.ui.formatter import FormatterPage
from resume_writer.ui.settings import SettingsPage
from resume_writer.ui.shell import AppShell


class ResumeWriterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Resume Writer {APP_VERSION}")
        self.geometry("1060x880")
        self.minsize(860, 700)

        self.dark_mode_var = tk.BooleanVar(value=True)
        self.font_var = tk.StringVar(value=str(DEFAULT_FORMAT_VALUES["font_name"]))
        self.name_size_var = tk.StringVar(value=str(DEFAULT_FORMAT_VALUES["name_size"]))
        self.heading_size_var = tk.StringVar(value=str(DEFAULT_FORMAT_VALUES["heading_size"]))
        self.body_size_var = tk.StringVar(value=str(DEFAULT_FORMAT_VALUES["body_size"]))
        self.output_dir_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.output_name_part_var = tk.StringVar(value="")
        self.output_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR / default_output_filename_for()))
        self.output_warning_var = tk.StringVar(value="")
        self.name_var = tk.StringVar(value=AUTHOR_NAME)
        self.email_var = tk.StringVar(value=EMAIL)
        self.phone_var = tk.StringVar(value=PHONE)
        self.location_var = tk.StringVar(value=LOCATION)
        self.masters_var = tk.BooleanVar(value=True)
        self.bachelors_var = tk.BooleanVar(value=False)
        self.summary_count_var = tk.StringVar(value="Summary: 0 words (required: 41-50)")
        self.validation_var = tk.StringVar(value="")

        self._widgets_by_role = {}
        self._submit_widgets = []
        self._suppress_output_path_refresh = False
        self._pages: dict[str, tk.Widget] = {}
        self.theme_toggle = None
        self.shell: Optional[AppShell] = None
        self.auth_view: Optional[AuthView] = None

        self._configure_style()
        self._build_menu()
        self._build_root_containers()
        self._bind_shortcuts()
        self._wire_validation()

        if user_auth.get_current_user():
            self._enter_authenticated_shell(user_auth.get_current_profile())
        else:
            self._show_auth()

    def _build_root_containers(self) -> None:
        self.auth_container = self._track(tk.Frame(self, bg=self.c("app_bg")), "app_frame")
        self.shell_container = self._track(tk.Frame(self, bg=self.c("app_bg")), "app_frame")

        self.auth_view = AuthView(
            self.auth_container,
            app=self,
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
            on_theme_toggle=self._toggle_theme,
        )
        self.documentation_page = DocumentationPage(self.shell.content, app=self)

        self._pages = {
            "writer": self.writer_page,
            "formatter": self.formatter_page,
            "settings": self.settings_page,
            "documentation": self.documentation_page,
        }
        for page in self._pages.values():
            page.place(x=0, y=0, relwidth=1, relheight=1)

        self._build_writer_ui(self.writer_page)
        self._update_validation_state()

    def _show_auth(self) -> None:
        self.shell_container.pack_forget()
        self.auth_container.pack(fill=tk.BOTH, expand=True)
        if self.auth_view is not None:
            self.auth_view.clear_form(mode="signin")
            self.auth_view.focus_username()

    def _enter_authenticated_shell(self, profile) -> None:
        self.dark_mode_var.set(bool(getattr(profile, "dark_mode", True)))
        self._configure_style()
        self._apply_theme()
        self._refresh_custom_controls()

        if self.shell is not None:
            self.shell.set_signed_in_label(
                display_name=getattr(profile, "display_name", "") or "",
                username=getattr(profile, "username", "") or "",
            )
            self.shell.apply_default_collapse_for_width(self.winfo_width() or 1060)

        self._apply_primary_format_from_store()
        self.auth_container.pack_forget()
        self.shell_container.pack(fill=tk.BOTH, expand=True)
        if self.shell is not None:
            self.shell.navigate("writer")
        self._schedule_update_check()

    def _schedule_update_check(self) -> None:
        """Weekly public GitHub Releases check after the main shell is ready."""
        try:
            from resume_writer.update import schedule_launch_update_check

            schedule_launch_update_check(self)
        except Exception:
            # Updater must never block or crash sign-in / shell entry.
            pass

    def _logout(self) -> None:
        user_auth.clear_session()
        self._show_auth()

    def _refresh_sidebar_user_label(self) -> None:
        if self.shell is None:
            return
        try:
            profile = user_auth.get_current_profile()
        except user_auth.AuthError:
            return
        self.shell.set_signed_in_label(
            display_name=profile.display_name,
            username=profile.username,
        )

    def _show_page(self, page_key: str) -> None:
        page = self._pages.get(page_key)
        if page is None:
            return
        page.lift()
        if page_key == "formatter" and hasattr(self, "formatter_page"):
            self.formatter_page.refresh()
        elif page_key == "settings" and hasattr(self, "settings_page"):
            # Refresh profile fields without re-applying theme from disk every time
            # in a way that fights an in-progress toggle — load profile values only.
            try:
                profile = user_auth.get_current_profile()
                self.settings_page.username_var.set(profile.username)
                self.settings_page.display_name_var.set(profile.display_name)
                self.settings_page.email_var.set(profile.email)
            except Exception:
                pass
            if self.theme_toggle is not None:
                self._draw_theme_toggle()
        elif page_key == "documentation" and hasattr(self, "documentation_page"):
            self.documentation_page.refresh()

    def _apply_primary_format_from_store(self) -> None:
        fmt = resume_format_from_store()
        self._apply_format_to_writer_controls(fmt)

    def _apply_primary_format(self, spec) -> None:
        try:
            kwargs = spec.to_writer_kwargs()
            self._apply_format_to_writer_controls(ResumeFormat(**kwargs))
        except Exception:
            self._apply_primary_format_from_store()

    def _apply_format_to_writer_controls(self, fmt: ResumeFormat) -> None:
        self.font_var.set(str(fmt.font_name))
        self.name_size_var.set(str(fmt.name_size))
        self.heading_size_var.set(str(fmt.heading_size))
        self.body_size_var.set(str(fmt.body_size))

    def _build_writer_ui(self, root) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        pad = self._track(tk.Frame(root, bg=self.c("app_bg"), padx=16, pady=16), "app_frame")
        pad.pack(fill=tk.BOTH, expand=True)
        pad.columnconfigure(0, weight=1)
        pad.rowconfigure(1, weight=1)

        controls = self._section(pad, "Format Options")
        controls.grid(row=0, column=0, sticky="ew")
        for column in range(8):
            controls.columnconfigure(column, weight=1 if column in (1, 3, 5, 7) else 0)

        self._combo(controls, "Font", self.font_var, FONT_CHOICES, 0, 0)
        self._combo(controls, "Name Size", self.name_size_var, NAME_SIZE_CHOICES, 0, 2)
        self._combo(controls, "Heading Size", self.heading_size_var, HEADING_SIZE_CHOICES, 0, 4)
        self._combo(controls, "Text Size", self.body_size_var, BODY_SIZE_CHOICES, 0, 6)

        text_area = self._track(tk.Frame(pad, bg=self.c("app_bg")), "app_frame")
        text_area.grid(row=1, column=0, sticky="nsew", pady=(12, 12))
        text_area.columnconfigure(0, weight=1)
        text_area.columnconfigure(1, weight=1)
        text_area.rowconfigure(1, weight=1, minsize=96)
        text_area.rowconfigure(4, weight=1, minsize=96)
        text_area.rowconfigure(6, weight=1, minsize=96)

        self.summary_text = self._text_box(text_area, "Summary", 0, 0, height=7)
        self.skills_text = self._text_box(text_area, "Skills", 0, 1, height=7)
        summary_footer = self._label(text_area, "", muted=True)
        summary_footer.configure(textvariable=self.summary_count_var)
        summary_footer.grid(row=2, column=0, sticky="w", pady=(0, 8))
        self.experience_text = self._text_box(text_area, "Job Experience", 3, 0, columnspan=2, height=7)
        self.certifications_text = self._text_box(text_area, "Certifications", 5, 0, height=7)
        self.top_skills_text = self._text_box(text_area, "Top 5 Skills For Metadata", 5, 1, height=7)

        output = self._section(pad, "Output")
        output.grid(row=2, column=0, sticky="ew")
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

        header = self._section(pad, "Header And Education")
        header.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        for column in range(4):
            header.columnconfigure(column, weight=1)

        self._entry(header, self.name_var).grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 8))
        self._entry(header, self.email_var).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(0, 8))
        self._entry(header, self.phone_var).grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=(0, 8))
        self._entry(header, self.location_var).grid(row=0, column=3, sticky="ew", pady=(0, 8))

        education_controls = self._track(tk.Frame(header, bg=self.c("panel_bg")), "panel_frame")
        education_controls.grid(row=1, column=0, columnspan=4, sticky="w")
        self.masters_choice = self._choice_label(education_controls, "Masters", self.masters_var, self._toggle_masters)
        self.masters_choice.pack(side=tk.LEFT)
        self._icon_button(education_controls, "✎", lambda: self._show_education_editor("masters")).pack(side=tk.LEFT, padx=(4, 18))
        self.bachelors_choice = self._choice_label(education_controls, "Bachelors", self.bachelors_var, self._toggle_bachelors)
        self.bachelors_choice.pack(side=tk.LEFT)
        self._icon_button(education_controls, "✎", lambda: self._show_education_editor("bachelors")).pack(side=tk.LEFT, padx=(4, 0))

        self.education_editor_frame = self._track(tk.Frame(header, bg=self.c("panel_bg")), "panel_frame")
        self.education_editor_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.education_editor_frame.columnconfigure(0, weight=1)
        self.education_editor_label = self._label(self.education_editor_frame, "Masters Education")
        self.education_editor_label.grid(row=0, column=0, sticky="w")
        self.masters_education_text = self._text_widget(self.education_editor_frame, height=3)
        self.bachelors_education_text = self._text_widget(self.education_editor_frame, height=3)
        self.masters_education_text.insert("1.0", DEFAULT_MASTERS_EDUCATION)
        self.bachelors_education_text.insert("1.0", DEFAULT_BACHELORS_EDUCATION)
        self.masters_education_text.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.bachelors_education_text.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.education_editor_frame.grid_remove()
        self.bachelors_education_text.grid_remove()

    def _build_ui(self) -> None:
        # Back-compat alias; writer UI is built into the shell writer page.
        if hasattr(self, "writer_page"):
            self._build_writer_ui(self.writer_page)

    def _configure_style(self) -> None:
        self.theme = THEMES["dark" if self.dark_mode_var.get() else "light"]
        self.option_add("*Font", "Arial 12")
        self.option_add("*Background", self.c("app_bg"))
        self.option_add("*Foreground", self.c("text_fg"))
        self.option_add("*Entry.Background", self.c("text_bg"))
        self.option_add("*Entry.Foreground", self.c("text_fg"))
        self.option_add("*Text.Background", self.c("text_bg"))
        self.option_add("*Text.Foreground", self.c("text_fg"))
        self.option_add("*insertBackground", self.c("text_fg"))
        self.configure(bg=self.c("app_bg"))

    def c(self, key: str) -> str:
        return self.theme[key]

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label="Usage Help", command=self._show_usage_help)
        help_menu.add_separator()
        help_menu.add_command(label="About Resume Writer", command=self._show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menu_bar)

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About Resume Writer",
            f"Resume Writer\n{APP_VERSION}",
        )

    def _show_usage_help(self) -> None:
        how_to = load_how_to_use_section()
        messagebox.showinfo("Usage Help", how_to[:1800] + ("…" if len(how_to) > 1800 else ""))

    def _section(self, parent, label: str) -> tk.LabelFrame:
        return self._track(tk.LabelFrame(
            parent,
            text=label,
            bg=self.c("panel_bg"),
            fg=self.c("text_fg"),
            padx=12,
            pady=12,
            bd=1,
            relief=tk.SOLID,
            font=("Arial", 12, "bold"),
            highlightbackground=self.c("border"),
            highlightcolor=self.c("border"),
        ), "section")

    def _label(self, parent, text: str, *, muted: bool = False) -> tk.Label:
        role = "muted_label" if muted else "label"
        return self._track(tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=self.c("muted_fg") if muted else self.c("text_fg"),
            anchor="w",
        ), role)

    def _entry(self, parent, variable: tk.StringVar, *, width: Optional[int] = None) -> tk.Entry:
        options = {}
        if width is not None:
            options["width"] = width
        entry = self._track(tk.Entry(
            parent,
            textvariable=variable,
            bg=self.c("text_bg"),
            fg=self.c("text_fg"),
            insertbackground=self.c("text_fg"),
            relief=tk.SOLID,
            bd=1,
            highlightthickness=1,
            highlightbackground=self.c("border"),
            highlightcolor=self.c("accent"),
            **options,
        ), "entry")
        entry.bind("<Return>", lambda _event: self.focus_get().tk_focusNext().focus_set() or "break")
        return entry

    def _button(self, parent, text: str, command, *, accent: bool = False) -> tk.Label:
        role = "accent_button" if accent else "button"
        button = self._track(tk.Label(
            parent,
            text=text,
            bg=self.c("accent") if accent else self.c("button_bg"),
            fg="#ffffff" if accent else self.c("text_fg"),
            activebackground=self.c("accent") if accent else self.c("button_active"),
            activeforeground="#ffffff" if accent else self.c("text_fg"),
            disabledforeground=self.c("disabled_fg"),
            relief=tk.RAISED,
            bd=1,
            padx=10,
            pady=5,
            cursor="hand2",
        ), role)
        button.normal_text = text
        button.is_accent = accent
        button.button_command = command
        button.bind("<Button-1>", self._invoke_label_button)
        button.bind("<Enter>", self._button_hover_enter)
        button.bind("<Leave>", self._button_hover_leave)
        return button

    def _invoke_label_button(self, event) -> None:
        widget = event.widget
        if not self._widget_alive(widget):
            self._prune_tracked_widgets()
            return
        try:
            if str(widget.cget("state")) != tk.DISABLED:
                widget.button_command()
        except tk.TclError:
            self._prune_tracked_widgets()

    def _button_hover_enter(self, event) -> None:
        widget = event.widget
        if not self._widget_alive(widget):
            return
        try:
            if str(widget.cget("state")) == tk.DISABLED:
                widget.configure(cursor="pirate")
            else:
                widget.configure(cursor="hand2")
        except tk.TclError:
            return

    def _button_hover_leave(self, event) -> None:
        widget = event.widget
        if not self._widget_alive(widget):
            self._prune_tracked_widgets()
            return
        try:
            widget.configure(text=widget.normal_text)
        except tk.TclError:
            self._prune_tracked_widgets()
            return
        self._apply_button_state()

    def _icon_button(self, parent, text: str, command) -> tk.Label:
        icon = self._track(tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=self.c("accent"),
            padx=2,
            cursor="hand2",
            font=("Arial", 14, "bold"),
        ), "icon_label")
        icon.bind("<Button-1>", lambda _event: command())
        return icon

    def _toggle_button(self, parent, variable: tk.BooleanVar, command) -> tk.Frame:
        frame = self._track(tk.Frame(parent, bg=parent.cget("bg"), cursor="hand2"), "toggle_frame")
        canvas = self._track(tk.Canvas(
            frame,
            width=48,
            height=26,
            bg=parent.cget("bg"),
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        ), "toggle_canvas")
        label = self._track(tk.Label(
            frame,
            text="Light Mode",
            bg=parent.cget("bg"),
            fg=self.c("toggle_text"),
            padx=6,
            cursor="hand2",
            font=("Arial", 12),
        ), "toggle_label")
        canvas.pack(side=tk.LEFT)
        label.pack(side=tk.LEFT)
        for widget in (frame, canvas, label):
            widget.bind("<Button-1>", lambda _event: command())
        frame.toggle_canvas = canvas
        frame.toggle_label = label
        return frame

    def _choice_label(self, parent, text: str, variable: tk.BooleanVar, command) -> tk.Label:
        choice = self._track(tk.Label(
            parent,
            bg=parent.cget("bg"),
            fg=self.c("text_fg"),
            padx=2,
            cursor="hand2",
            font=("Arial", 13),
        ), "choice_label")
        choice.choice_text = text
        choice.choice_var = variable
        choice.bind("<Button-1>", lambda _event: command())
        return choice

    def _combo(self, parent, label: str, variable: tk.StringVar, values: tuple[str, ...], row: int, column: int) -> None:
        self._label(parent, label).grid(row=row, column=column, sticky="w", padx=(0, 6))
        dropdown = tk.OptionMenu(parent, variable, *values)
        dropdown.configure(
            bg=self.c("text_bg"),
            fg=self.c("text_fg"),
            activebackground=self.c("button_active"),
            activeforeground=self.c("text_fg"),
            relief=tk.SOLID,
            bd=1,
            highlightthickness=1,
            highlightbackground=self.c("border"),
            highlightcolor=self.c("accent"),
            anchor="w",
            width=14,
            cursor="hand2",
        )
        dropdown["menu"].configure(
            bg=self.c("text_bg"),
            fg=self.c("text_fg"),
            activebackground=self.c("button_active"),
            activeforeground=self.c("text_fg"),
        )
        self._track(dropdown, "option")
        self._track(dropdown["menu"], "menu")
        dropdown.grid(row=row, column=column + 1, sticky="ew", padx=(0, 12))

    def _text_box(
        self,
        parent,
        label: str,
        row: int,
        column: int,
        columnspan: int = 1,
        height: int = 8,
        footer_var: Optional[tk.StringVar] = None,
    ) -> tk.Text:
        self._label(parent, label).grid(row=row, column=column, columnspan=columnspan, sticky="w")
        frame = self._track(tk.Frame(parent, bg=self.c("panel_bg")), "panel_frame")
        frame.grid(row=row + 1, column=column, columnspan=columnspan, sticky="nsew", padx=(0, 8), pady=(4, 12))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = self._text_widget(frame, height=height)
        text.grid(row=0, column=0, sticky="nsew")
        if footer_var is not None:
            footer = self._label(frame, "", muted=True)
            footer.configure(textvariable=footer_var)
            footer.grid(row=1, column=0, sticky="w", pady=(4, 0))
        return text

    def _text_widget(self, parent, height: int) -> tk.Text:
        text = self._track(tk.Text(
            parent,
            height=height,
            wrap=tk.WORD,
            undo=True,
            bg=self.c("text_bg"),
            fg=self.c("text_fg"),
            insertbackground=self.c("text_fg"),
            selectbackground=self.c("select_bg"),
            selectforeground=self.c("text_fg"),
            relief=tk.SOLID,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=self.c("border"),
            highlightcolor=self.c("accent"),
            font=("Arial", 12),
        ), "text")
        text.bind("<Tab>", self._focus_next)
        text.bind("<Shift-Tab>", self._focus_previous)
        text.bind("<KeyRelease>", lambda _event: self._update_validation_state())
        text.bind("<FocusOut>", lambda _event: self._update_validation_state())
        return text

    def _track(self, widget, role: str):
        self._widgets_by_role.setdefault(role, []).append(widget)
        self._add_submit_bindtag(widget)
        return widget

    def _widget_alive(self, widget) -> bool:
        try:
            return bool(widget.winfo_exists())
        except tk.TclError:
            return False

    def _prune_tracked_widgets(self) -> None:
        for role, widgets in list(self._widgets_by_role.items()):
            self._widgets_by_role[role] = [widget for widget in widgets if self._widget_alive(widget)]
        self._submit_widgets = [widget for widget in self._submit_widgets if self._widget_alive(widget)]

    def _add_submit_bindtag(self, widget) -> None:
        try:
            bindtags = widget.bindtags()
        except tk.TclError:
            return
        if "SubmitShortcut" not in bindtags:
            widget.bindtags(("SubmitShortcut", *bindtags))

    def _focus_next(self, event) -> str:
        event.widget.tk_focusNext().focus_set()
        return "break"

    def _focus_previous(self, event) -> str:
        event.widget.tk_focusPrev().focus_set()
        return "break"

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
        for variable in (
            self.name_var,
            self.email_var,
            self.phone_var,
            self.location_var,
            self.output_dir_var,
            self.output_name_part_var,
            self.output_var,
            self.masters_var,
            self.bachelors_var,
        ):
            variable.trace_add("write", lambda *_args: self._update_validation_state())
        self.output_name_part_var.trace_add("write", lambda *_args: self._refresh_output_path())
        self.output_dir_var.trace_add("write", lambda *_args: self._refresh_output_path())

    def _shortcut_generate(self, _event) -> str:
        if self._is_form_valid():
            self._generate()
        return "break"

    def _text_value(self, text_widget: tk.Text) -> str:
        return text_widget.get("1.0", tk.END).strip()

    def _summary_word_count(self) -> int:
        return count_words(self._text_value(self.summary_text))

    def _validation_errors(self) -> list[str]:
        errors = []
        summary_words = self._summary_word_count()
        if not self._text_value(self.summary_text):
            errors.append("Summary is required")
        elif summary_words <= 40 or summary_words > 50:
            errors.append("Summary must be 41-50 words")
        if not self._text_value(self.skills_text):
            errors.append("Skills are required")
        if not self._text_value(self.experience_text):
            errors.append("Job Experience is required")
        if not self._text_value(self.top_skills_text):
            errors.append("Top 5 Skills are required")
        if not self.output_name_part_var.get().strip():
            errors.append("File Name is required")
        if not self.output_var.get().strip():
            errors.append("Output file is required")
        if self._matching_existing_output_files():
            errors.append("A matching DOCX or PDF file already exists")
        return errors

    def _is_form_valid(self) -> bool:
        return not self._validation_errors()

    def _update_validation_state(self) -> None:
        if not hasattr(self, "summary_text"):
            return
        summary_words = self._summary_word_count()
        summary_ok = 40 < summary_words <= 50
        self.summary_count_var.set(f"Summary: {summary_words} words (required: 41-50)")
        errors = self._validation_errors()
        if errors:
            self.validation_var.set("Generate disabled: " + "; ".join(errors))
            submit_state = tk.DISABLED
        else:
            self.validation_var.set("Ready to generate.")
            submit_state = tk.NORMAL
        for widget in self._submit_widgets:
            if not self._widget_alive(widget):
                continue
            widget.configure(state=submit_state)
        self._refresh_custom_controls()
        self._apply_button_state()
        self._style_status_labels(summary_ok=summary_ok, form_ok=not errors)
        self._refresh_output_warning()

    def _style_status_labels(self, *, summary_ok: bool, form_ok: bool) -> None:
        for widget in self._widgets_by_role.get("muted_label", []):
            if not self._widget_alive(widget):
                continue
            try:
                widget.configure(fg=self.c("muted_fg"))
            except tk.TclError:
                pass
        if hasattr(self, "validation_label") and self._widget_alive(self.validation_label):
            self.validation_label.configure(fg=self.c("ok_fg") if form_ok else self.c("error_fg"))

    def _apply_button_state(self) -> None:
        # Prune destroyed dialog buttons (e.g. Formatter Add Format) so hover/generate
        # never touch invalid Tcl widget names.
        alive: list = []
        for widget in self._widgets_by_role.get("accent_button", []):
            if not self._widget_alive(widget):
                continue
            alive.append(widget)
            try:
                if str(widget.cget("state")) == tk.DISABLED:
                    widget.configure(
                        bg=self.c("disabled_bg"),
                        fg=self.c("disabled_fg"),
                        activebackground=self.c("disabled_bg"),
                        activeforeground=self.c("disabled_fg"),
                        disabledforeground=self.c("disabled_fg"),
                        cursor="arrow",
                    )
                else:
                    widget.configure(
                        bg=self.c("accent"),
                        fg="#ffffff",
                        activebackground=self.c("accent"),
                        activeforeground="#ffffff",
                        disabledforeground=self.c("disabled_fg"),
                        cursor="hand2",
                    )
            except tk.TclError:
                continue
        self._widgets_by_role["accent_button"] = alive
        # Also drop dead non-accent buttons from the generic button role.
        self._widgets_by_role["button"] = [
            widget for widget in self._widgets_by_role.get("button", []) if self._widget_alive(widget)
        ]
        self._submit_widgets = [widget for widget in self._submit_widgets if self._widget_alive(widget)]

    def _show_education_editor(self, education_key: str) -> None:
        self.education_editor_frame.grid()
        if education_key == "masters":
            self.education_editor_label.configure(text="Masters Education")
            self.bachelors_education_text.grid_remove()
            self.masters_education_text.grid()
        else:
            self.education_editor_label.configure(text="Bachelors Education")
            self.masters_education_text.grid_remove()
            self.bachelors_education_text.grid()

    def _toggle_masters(self) -> None:
        self.masters_var.set(not self.masters_var.get())
        self._update_validation_state()

    def _toggle_bachelors(self) -> None:
        self.bachelors_var.set(not self.bachelors_var.get())
        self._update_validation_state()

    def _refresh_custom_controls(self) -> None:
        if getattr(self, "theme_toggle", None) is not None:
            self._draw_theme_toggle()
        alive_choices = []
        for widget in self._widgets_by_role.get("choice_label", []):
            if not self._widget_alive(widget):
                continue
            alive_choices.append(widget)
            try:
                is_checked = bool(widget.choice_var.get())
                marker = "☑" if is_checked else "☐"
                widget.configure(text=f"{marker} {widget.choice_text}")
            except tk.TclError:
                continue
        self._widgets_by_role["choice_label"] = alive_choices

    def _draw_theme_toggle(self) -> None:
        if getattr(self, "theme_toggle", None) is None:
            return
        canvas = self.theme_toggle.toggle_canvas
        label = self.theme_toggle.toggle_label
        is_dark = self.dark_mode_var.get()
        canvas.delete("all")
        canvas.configure(bg=self.theme_toggle.cget("bg"))
        track = self.c("toggle_track") if is_dark else self.c("button_active")
        knob_x = 35 if is_dark else 13
        canvas.create_oval(1, 1, 25, 25, fill=track, outline=track)
        canvas.create_oval(23, 1, 47, 25, fill=track, outline=track)
        canvas.create_rectangle(13, 1, 35, 25, fill=track, outline=track)
        canvas.create_oval(knob_x - 10, 3, knob_x + 10, 23, fill=self.c("toggle_knob"), outline=self.c("toggle_knob"))
        label.configure(text="Dark Mode" if is_dark else "Light Mode", fg=self.c("toggle_text"))

    def _selected_education_entries(self) -> Tuple[str, ...]:
        entries = []
        if self.masters_var.get():
            entries.append(self._text_value(self.masters_education_text))
        if self.bachelors_var.get():
            entries.append(self._text_value(self.bachelors_education_text))
        return tuple(entry for entry in entries if entry.strip())

    def _toggle_theme(self) -> None:
        self.dark_mode_var.set(not self.dark_mode_var.get())
        self._configure_style()
        self._apply_theme()
        self._refresh_custom_controls()
        self._update_validation_state()

    def _apply_theme(self) -> None:
        self._prune_tracked_widgets()
        role_options = {
            "app_frame": {"bg": self.c("app_bg")},
            "panel_frame": {"bg": self.c("panel_bg")},
            "section": {
                "bg": self.c("panel_bg"),
                "fg": self.c("text_fg"),
                "highlightbackground": self.c("border"),
                "highlightcolor": self.c("border"),
            },
            "label": {"fg": self.c("text_fg")},
            "muted_label": {"fg": self.c("muted_fg")},
            "entry": {
                "bg": self.c("text_bg"),
                "fg": self.c("text_fg"),
                "insertbackground": self.c("text_fg"),
                "highlightbackground": self.c("border"),
                "highlightcolor": self.c("accent"),
            },
            "text": {
                "bg": self.c("text_bg"),
                "fg": self.c("text_fg"),
                "insertbackground": self.c("text_fg"),
                "selectbackground": self.c("select_bg"),
                "selectforeground": self.c("text_fg"),
                "highlightbackground": self.c("border"),
                "highlightcolor": self.c("accent"),
            },
            "button": {
                "bg": self.c("button_bg"),
                "fg": self.c("text_fg"),
                "activebackground": self.c("button_active"),
                "activeforeground": self.c("text_fg"),
                "disabledforeground": self.c("disabled_fg"),
                "cursor": "hand2",
            },
            "choice_label": {"fg": self.c("text_fg")},
            "toggle_frame": {},
            "toggle_canvas": {"bg": self.c("panel_bg")},
            "toggle_label": {"fg": self.c("toggle_text")},
            "icon_label": {"fg": self.c("accent")},
            "option": {
                "bg": self.c("text_bg"),
                "fg": self.c("text_fg"),
                "activebackground": self.c("button_active"),
                "activeforeground": self.c("text_fg"),
                "highlightbackground": self.c("border"),
                "highlightcolor": self.c("accent"),
            },
            "menu": {
                "bg": self.c("text_bg"),
                "fg": self.c("text_fg"),
                "activebackground": self.c("button_active"),
                "activeforeground": self.c("text_fg"),
            },
        }
        parent_bg_roles = {
            "label",
            "muted_label",
            "toggle_frame",
            "toggle_canvas",
            "icon_label",
        }
        parent_active_bg_roles = {"choice_label", "toggle_label"}
        for role, widgets in self._widgets_by_role.items():
            for widget in widgets:
                options = dict(role_options.get(role, {}))
                if role in parent_bg_roles:
                    try:
                        options["bg"] = widget.master.cget("bg")
                    except tk.TclError:
                        pass
                if role in parent_active_bg_roles:
                    try:
                        options["bg"] = widget.master.cget("bg")
                        options["activebackground"] = widget.master.cget("bg")
                    except tk.TclError:
                        pass
                try:
                    widget.configure(**options)
                except tk.TclError:
                    pass
        # Theme role defaults overwrite dynamic status colors; restore them.
        self._update_validation_state()
        # Sidebar chrome (collapsed flat icons / Sign Out) depends on expanded state.
        if self.shell is not None:
            self.shell._refresh_nav_styles()

    def _output_directory(self) -> Path:
        return Path(self.output_dir_var.get().strip() or str(DEFAULT_OUTPUT_DIR)).expanduser()

    def _applied_output_directory(self) -> Path:
        return self._output_directory() / "#applied"

    def _ensure_applied_output_directory(self) -> None:
        self._applied_output_directory().mkdir(parents=True, exist_ok=True)

    def _output_name_part(self) -> str:
        return re.sub(r"[^A-Za-z0-9_-]+", "", self.output_name_part_var.get().strip())

    def _output_path(self) -> Path:
        return self._output_directory() / default_output_filename_for(self._output_name_part())

    def _refresh_output_path(self) -> None:
        if not hasattr(self, "output_var"):
            return
        if self._suppress_output_path_refresh:
            return
        new_path = str(self._output_path())
        if self.output_var.get() != new_path:
            self.output_var.set(new_path)

    def _matching_existing_output_files(self) -> list[Path]:
        try:
            self._ensure_applied_output_directory()
        except OSError:
            return []
        return find_matching_output_files(self._output_directory(), self._output_name_part())

    def _refresh_output_warning(self) -> None:
        if not hasattr(self, "output_warning_var"):
            return
        matches = self._matching_existing_output_files()
        if matches:
            output_dir = self._output_directory()
            shown = ", ".join(str(path.relative_to(output_dir)) if path.is_relative_to(output_dir) else path.name for path in matches[:3])
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
                if not self.output_name_part_var.get().strip():
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
            self.output_dir_var.set(selected)
            self._refresh_output_path()
            self._update_validation_state()

    def _generate(self) -> None:
        try:
            # Full primary ResumeFormat from store (structure + page + typography).
            # Writer UI font dropdowns may override typography only; margins,
            # separators, headings, and experience layout always stay primary.
            stored = resume_format_from_store()
            fmt = replace(
                stored,
                font_name=self.font_var.get(),
                name_size=int(self.name_size_var.get()),
                heading_size=int(self.heading_size_var.get()),
                body_size=int(self.body_size_var.get()),
            )
            content = ResumeContent(
                name=self.name_var.get().strip(),
                email=self.email_var.get().strip(),
                phone=self.phone_var.get().strip(),
                location=self.location_var.get().strip(),
                summary=self.summary_text.get("1.0", tk.END).strip(),
                skills=self.skills_text.get("1.0", tk.END).strip(),
                experience=self.experience_text.get("1.0", tk.END).strip(),
                certifications=self.certifications_text.get("1.0", tk.END).strip(),
                top_skills=self.top_skills_text.get("1.0", tk.END).strip(),
                education_entries=self._selected_education_entries(),
            )
            if not self._is_form_valid():
                messagebox.showerror("Cannot generate resume", self.validation_var.get())
                return
            output_path = Path(self.output_var.get()).expanduser()
            if output_path.suffix.lower() != ".docx":
                output_path = output_path.with_suffix(".docx")
            build_resume(content, fmt, output_path)
        except Exception as exc:
            messagebox.showerror("Could not generate resume", str(exc))
            return
        self._clear_text_inputs()
        messagebox.showinfo("Resume generated", f"Saved to:\n{output_path}")

    def _clear_text_inputs(self) -> None:
        for text_widget in (
            self.summary_text,
            self.skills_text,
            self.experience_text,
            self.certifications_text,
            self.top_skills_text,
        ):
            text_widget.delete("1.0", tk.END)
        self._suppress_output_path_refresh = True
        try:
            self.output_name_part_var.set("")
        finally:
            self._suppress_output_path_refresh = False
        self._update_validation_state()
