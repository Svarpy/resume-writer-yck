"""Themed Tk widget factory and theme application (shared by every page of the desktop app).

``ThemedToolkit`` is a mixin for the main window: it relies on ``dark_mode_var``, ``settings`` and the
``_after_theme_applied`` hook that the application class provides.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from resume_gui.theme import THEMES


class ThemedToolkit:

    def c(self, key: str) -> str:
        return self.theme[key]

    def _configure_style(self) -> None:
        self.theme = dict(THEMES["dark" if self.dark_mode_var.get() else "light"])
        self.theme["accent"] = self.settings.get("appearance.accent_color")
        self.option_add("*Font", "Arial 12")
        self.option_add("*Background", self.c("app_bg"))
        self.option_add("*Foreground", self.c("text_fg"))
        self.option_add("*Entry.Background", self.c("text_bg"))
        self.option_add("*Entry.Foreground", self.c("text_fg"))
        self.option_add("*Text.Background", self.c("text_bg"))
        self.option_add("*Text.Foreground", self.c("text_fg"))
        self.option_add("*insertBackground", self.c("text_fg"))
        self.configure(bg=self.c("app_bg"))

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
            font=("Arial", self.settings.get("appearance.editor_font_size")),
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

    def _refresh_custom_controls(self) -> None:
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
            "card": {"bg": self.c("panel_bg"), "highlightbackground": self.c("border")},
            "canvas": {"bg": self.c("app_bg")},
            "choice_label": {"fg": self.c("text_fg")},
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
            "icon_label",
        }
        parent_active_bg_roles = {"choice_label"}
        # Two passes: containers first, then widgets that copy their parent's
        # background. A single pass left labels with the previous theme's
        # background whenever their frame had not been restyled yet.
        child_roles = parent_bg_roles | parent_active_bg_roles
        ordered_roles = [r for r in self._widgets_by_role if r not in child_roles]
        ordered_roles += [r for r in self._widgets_by_role if r in child_roles]
        for role in ordered_roles:
            for widget in self._widgets_by_role[role]:
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
        self._after_theme_applied()

    # ------------------------------------------------------------------
    # Output path and duplicate check (Settings > Output, Settings > Duplicate Check)
    # ------------------------------------------------------------------
