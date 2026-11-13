"""Settings page: every customisable option, grouped by category, editable like VS Code.

The page is generated from :mod:`resume_core.settings.schema`. Changes are
validated and written to the user's ``settings.json`` immediately (through the
``Settings`` object the app owns); ``Edit settings.json`` opens the raw file for
hand editing.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Callable, Optional

from resume_client import ClientError
from resume_core.settings import (
    FieldDef,
    Settings,
    SettingDef,
    SettingsError,
    categories,
    known_field_keys,
    settings_in_category,
)

ALL_CATEGORIES = "All Settings"
FIELDS_PER_LINE = 4


class SettingsPage(tk.Frame):
    def __init__(self, parent, *, app) -> None:
        super().__init__(parent, bg=app.c("app_bg"), padx=16, pady=16)
        self.app = app

        self.search_var = tk.StringVar()
        self.selected_category = ALL_CATEGORIES
        self._rows: dict[str, dict[str, Any]] = {}
        self._info_labels: dict[str, tk.Label] = {}
        self._category_buttons: dict[str, tk.Label] = {}
        self._building = False
        self._rejected: dict[str, str] = {}      # typed values that failed validation (not applied)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_chrome()
        self.search_var.trace_add("write", lambda *_a: self._rebuild_list())
        self._rebuild_list()

    # ------------------------------------------------------------------
    # Chrome: title bar, category list, scrolling body, JSON editor
    # ------------------------------------------------------------------
    def _build_chrome(self) -> None:
        app = self.app
        bar = app._track(tk.Frame(self, bg=app.c("app_bg")), "app_frame")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bar.columnconfigure(1, weight=1)
        title = app._label(bar, "Settings")
        title.configure(font=("Arial", 16, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=(0, 16))
        self.search_entry = app._entry(bar, self.search_var)
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        self.json_button = app._button(bar, "Edit settings.json", self._show_json_editor)
        self.json_button.grid(row=0, column=2, padx=(0, 8))
        app._button(bar, "Reset All", self._reset_all).grid(row=0, column=3)
        self.hint_label = app._label(
            bar,
            "Type to search. Changes apply here at once; press Save Settings (bottom right) to store them.",
            muted=True,
        )
        self.hint_label.grid(row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))
        self.format_label = app._label(bar, "", muted=True)
        self.format_label.grid(row=2, column=0, columnspan=5, sticky="w")
        self.save_label = app._label(bar, "")
        self.save_label.configure(fg=app.c("error_fg"), wraplength=900, justify=tk.LEFT)
        self.save_label.grid(row=3, column=0, columnspan=5, sticky="w")

        self.body = app._track(tk.Frame(self, bg=app.c("app_bg")), "app_frame")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.columnconfigure(1, weight=1)
        self.body.rowconfigure(0, weight=1)

        nav = app._track(tk.Frame(self.body, bg=app.c("panel_bg"), padx=6, pady=6), "panel_frame")
        nav.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        for name in (ALL_CATEGORIES, *categories()):
            button = app._button(nav, name, lambda n=name: self._select_category(n))
            button.configure(anchor="w")
            button.pack(fill=tk.X, pady=2)
            self._category_buttons[name] = button
        # Pinned to the bottom of the left column; administrators only (see _sync_admin_visibility).
        self.backup_button = app._button(nav, "Download Backup", self.app.download_backup)
        self.backup_button.configure(anchor="w")

        self.list_view = app._track(tk.Frame(self.body, bg=app.c("app_bg")), "app_frame")
        self.list_view.grid(row=0, column=1, sticky="nsew")
        self.list_view.columnconfigure(0, weight=1)
        self.list_view.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self.list_view, bg=app.c("app_bg"), highlightthickness=0, bd=0)
        app._track(self.canvas, "canvas")
        self.scrollbar = tk.Scrollbar(self.list_view, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.inner = app._track(tk.Frame(self.canvas, bg=app.c("app_bg")), "app_frame")
        self._inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._inner_window, width=e.width))
        self.inner.columnconfigure(0, weight=1)

        self.json_view = app._track(tk.Frame(self.body, bg=app.c("app_bg")), "app_frame")
        self.json_view.grid(row=0, column=1, sticky="nsew")
        self.json_view.columnconfigure(0, weight=1)
        self.json_view.rowconfigure(1, weight=1)
        self.json_help = app._label(
            self.json_view,
            "settings.json — edit the complete settings file. Save validates every value before applying it.",
            muted=True,
        )
        self.json_help.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.json_text = self._plain_text(self.json_view, height=20)
        self.json_text.grid(row=1, column=0, sticky="nsew")
        json_scroll = tk.Scrollbar(self.json_view, orient=tk.VERTICAL, command=self.json_text.yview)
        self.json_text.configure(yscrollcommand=json_scroll.set)
        json_scroll.grid(row=1, column=1, sticky="ns")
        json_actions = app._track(tk.Frame(self.json_view, bg=app.c("app_bg")), "app_frame")
        json_actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        app._button(json_actions, "Save", self._save_json, accent=True).pack(side=tk.LEFT)
        app._button(json_actions, "Revert", self._load_json_text).pack(side=tk.LEFT, padx=8)
        app._button(json_actions, "Back To Settings", self._show_list_view).pack(side=tk.LEFT)
        self.json_error = app._label(self.json_view, "")
        self.json_error.configure(fg=app.c("error_fg"), wraplength=700, justify=tk.LEFT)
        self.json_error.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.json_view.grid_remove()

        footer = app._track(tk.Frame(self, bg=app.c("app_bg")), "app_frame")
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        self.status_label = app._label(footer, "All changes saved.", muted=True)
        self.status_label.grid(row=0, column=0, sticky="w")
        self.discard_button = app._button(footer, "Discard Changes", self._discard)
        self.discard_button.grid(row=0, column=1, padx=(0, 8))
        self.save_button = app._button(footer, "Save Settings", self._save, accent=True)
        self.save_button.grid(row=0, column=2)
        self.update_save_bar()

    def scroll_target(self):
        """What the app-wide wheel/trackpad handler scrolls on this page."""
        return self.json_text if self.json_view.winfo_ismapped() else self.canvas

    def _plain_text(self, parent, height: int) -> tk.Text:
        """A themed Text box that does not trigger Writer validation while typing."""
        text = self.app._text_widget(parent, height=height)
        text.unbind("<KeyRelease>")
        text.unbind("<FocusOut>")
        return text

    # ------------------------------------------------------------------
    # Page lifecycle
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Called whenever the page is shown or the settings object was reloaded."""
        self.format_label.configure(
            text=f"Resume format: {self.app.current_format_name()}.  Settings marked 'format' belong to this "
                 "format and change when you pick another one in the Formatter; the rest apply to every format."
        )
        self._sync_admin_visibility()
        self._show_list_view()
        self._rebuild_list()

    def _is_admin(self) -> bool:
        return bool(self.app.client.is_admin)

    def _sync_admin_visibility(self) -> None:
        """Show the Backup button (bottom of the left column) to administrators only; the role is re-read each time."""
        try:
            self.app.client.profile()
        except ClientError:
            pass  # keep the last known role when the server cannot be reached
        if self._is_admin():
            if not self.backup_button.winfo_manager():
                self.backup_button.pack(side=tk.BOTTOM, fill=tk.X, pady=2)
        else:
            self.backup_button.pack_forget()

    # ------------------------------------------------------------------
    # Save / discard
    # ------------------------------------------------------------------
    def has_rejected_values(self) -> bool:
        return bool(self._rejected)

    def show_rejected_values(self) -> None:
        self.save_label.configure(text="Not saved: fix " + "; ".join(self._rejected.values()))

    def discard_typed_values(self) -> None:
        """Rebuild the controls from the (reverted) settings, dropping anything typed but never applied."""
        self._rejected.clear()
        self._rebuild_list()
        self.update_save_bar()

    def update_save_bar(self) -> None:
        """Enable Save / Discard only while there is something to save."""
        if not hasattr(self, "save_button"):
            return
        dirty = self.app.settings_dirty()
        state = tk.NORMAL if dirty else tk.DISABLED
        for button in (self.save_button, self.discard_button):
            button.configure(state=state)
        self.status_label.configure(text="You have unsaved changes." if dirty else "All changes saved.")
        self.app._refresh_custom_controls()

    def _save(self) -> None:
        self.app.save_settings_draft()

    def _discard(self) -> None:
        if self.app.settings_dirty() and messagebox.askyesno("Discard Changes", "Discard every unsaved change?"):
            self.app.discard_settings_draft()

    def show_save_error(self, message: str) -> None:
        """Show (or clear) a message when settings could not be saved to the server."""
        try:
            self.save_label.configure(text=f"Not saved: {message}" if message else "")
        except tk.TclError:
            pass

    def on_settings_changed(self, _keys: tuple[str, ...] = ()) -> None:
        """Keep markers, info rows and the JSON view in step with the settings."""
        if self._building:
            return
        for key in self._rows:
            self._refresh_row_state(key)
        self._refresh_info_rows()
        if self.json_view.winfo_ismapped():
            self._load_json_text()

    def _select_category(self, name: str) -> None:
        self.selected_category = name
        self._show_list_view()
        self._rebuild_list()

    def _show_list_view(self) -> None:
        self.json_view.grid_remove()
        self.list_view.grid()
        self.json_button.configure(text="Edit settings.json")

    # ------------------------------------------------------------------
    # Building the setting list
    # ------------------------------------------------------------------
    def _matching(self, definition: SettingDef) -> bool:
        terms = self.search_var.get().strip().casefold().split()
        if not terms:
            return True
        haystack = f"{definition.category} {definition.label} {definition.key} {definition.description}".casefold()
        return all(term in haystack for term in terms)

    def _rebuild_list(self) -> None:
        self._rejected.clear()                    # the controls are rebuilt from the settings
        self._building = True
        try:
            for child in self.inner.winfo_children():
                child.destroy()
            self._rows.clear()
            self._info_labels.clear()
            row_index = 0
            shown = 0
            for category in categories():
                if self.selected_category not in (ALL_CATEGORIES, category):
                    continue
                matches = [d for d in settings_in_category(category) if self._matching(d)]
                if not matches:
                    continue
                header = self.app._label(self.inner, category)
                header.configure(font=("Arial", 14, "bold"))
                header.grid(row=row_index, column=0, sticky="w", pady=(14 if shown else 0, 4))
                row_index += 1
                for definition in matches:
                    self._build_setting(definition).grid(row=row_index, column=0, sticky="ew", pady=(0, 10), padx=(0, 8))
                    row_index += 1
                    shown += 1
            if not shown:
                self.app._label(self.inner, "No settings match your search.", muted=True).grid(
                    row=0, column=0, sticky="w"
                )
            for name, button in self._category_buttons.items():
                self._style_category_button(name, button)
            self.app._prune_tracked_widgets()
            self.canvas.yview_moveto(0)
        finally:
            self._building = False
        self._refresh_info_rows()

    def _style_category_button(self, name: str, button: tk.Label) -> None:
        active = name == self.selected_category
        try:
            button.configure(
                bg=self.app.c("accent") if active else self.app.c("button_bg"),
                fg="#ffffff" if active else self.app.c("text_fg"),
                activebackground=self.app.c("accent") if active else self.app.c("button_active"),
                activeforeground="#ffffff" if active else self.app.c("text_fg"),
            )
        except tk.TclError:
            pass

    def restyle(self) -> None:
        """Re-apply selection and status colours after a theme change."""
        for name, button in self._category_buttons.items():
            self._style_category_button(name, button)
        try:
            for row in self._rows.values():
                row["error"].configure(fg=self.app.c("error_fg"))
                row["marker"].configure(fg=self.app.c("accent"))
            self.json_error.configure(fg=self.app.c("error_fg"))
        except tk.TclError:
            pass

    def _build_setting(self, definition: SettingDef) -> tk.Frame:
        app = self.app
        card = app._track(tk.Frame(self.inner, bg=app.c("panel_bg"), padx=12, pady=10, highlightthickness=1,
                                   highlightbackground=app.c("border")), "card")
        card.columnconfigure(0, weight=1)

        head = app._track(tk.Frame(card, bg=app.c("panel_bg")), "panel_frame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        title = app._label(head, definition.label)
        title.configure(font=("Arial", 12, "bold"))
        title.grid(row=0, column=0, sticky="w")
        if definition.scope == "format":
            badge = app._label(head, "format", muted=True)
            badge.configure(font=("Arial", 10, "italic"))
            badge.grid(row=0, column=3, padx=(8, 0))
        marker = app._label(head, "")
        marker.configure(fg=app.c("accent"), font=("Arial", 11, "bold"))
        marker.grid(row=0, column=1, padx=(8, 0))
        reset = app._button(head, "Reset", lambda k=definition.key: self._reset_one(k))
        reset.configure(padx=6, pady=1, font=("Arial", 10))
        if definition.description:
            description = app._label(card, definition.description, muted=True)
            description.configure(wraplength=620, justify=tk.LEFT)
            description.grid(row=1, column=0, sticky="w", pady=(2, 6))

        holder = app._track(tk.Frame(card, bg=app.c("panel_bg")), "panel_frame")
        holder.grid(row=2, column=0, sticky="ew")
        holder.columnconfigure(0, weight=1)
        error = app._label(card, "")
        error.configure(fg=app.c("error_fg"), wraplength=620, justify=tk.LEFT)
        error.grid(row=3, column=0, sticky="w")

        apply_value = self._build_control(definition, holder, error)
        self._rows[definition.key] = {
            "marker": marker,
            "reset": reset,
            "error": error,
            "apply": apply_value,
            "definition": definition,
        }
        self._refresh_row_state(definition.key)
        return card

    def _refresh_row_state(self, key: str) -> None:
        row = self._rows.get(key)
        if row is None or not row["definition"].stored:
            return
        try:
            modified = not self.app.settings.is_default(key)
            row["marker"].configure(text="●" if modified else "")
            if modified:
                row["reset"].grid(row=0, column=2, padx=(8, 0))
            else:
                row["reset"].grid_remove()
        except tk.TclError:
            pass

    def _refresh_info_rows(self) -> None:
        for key, label in list(self._info_labels.items()):
            try:
                if key == "output.preview":
                    label.configure(text=self.app.output_preview_text())
            except tk.TclError:
                continue

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------
    def _build_control(self, definition: SettingDef, holder: tk.Frame, error: tk.Label) -> Callable[[Any], None]:
        builders = {
            "bool": self._control_bool,
            "str": self._control_entry,
            "path": self._control_entry,
            "color": self._control_entry,
            "int": self._control_entry,
            "choice": self._control_choice,
            "str_list": self._control_list,
            "int_list": self._control_list,
            "checklist": self._control_checklist,
            "records": self._control_records,
            "info": self._control_info,
        }
        return builders[definition.kind](definition, holder, error)

    def _commit(self, definition: SettingDef, value: Any, error: tk.Label, *, quiet: bool = False) -> bool:
        """Validate and save. ``quiet`` is used while typing: a half-typed value is simply not saved yet."""
        try:
            with self.app.settings_edit():
                self.app.settings.set(definition.key, value)
        except SettingsError as exc:
            self._rejected[definition.key] = f"{definition.label}: {exc}"
            if not quiet:
                error.configure(text=str(exc))
            self.update_save_bar()
            return False
        self._rejected.pop(definition.key, None)
        error.configure(text="")
        self.update_save_bar()
        return True

    def _control_bool(self, definition, holder, error):
        variable = tk.BooleanVar(value=bool(self.app.settings.get(definition.key)))

        def toggle() -> None:
            wanted = not variable.get()
            if self._commit(definition, wanted, error):
                variable.set(wanted)
                self.app._refresh_custom_controls()

        choice = self.app._choice_label(holder, "Enabled", variable, toggle)
        choice.grid(row=0, column=0, sticky="w")
        self.app._refresh_custom_controls()
        return lambda value: variable.set(bool(value))

    def _control_entry(self, definition, holder, error):
        variable = tk.StringVar(value=str(self.app.settings.get(definition.key)))
        entry = self.app._entry(holder, variable, width=46 if definition.kind != "int" else 10)
        entry.grid(row=0, column=0, sticky="w")
        column = 1

        swatch = None
        if definition.kind == "color":
            swatch = tk.Label(holder, width=3, bd=1, relief=tk.SOLID)
            swatch.grid(row=0, column=column, padx=(8, 0))
            column += 1

            def paint(*_a) -> None:
                try:
                    swatch.configure(bg=variable.get().strip() or self.app.c("panel_bg"))
                except tk.TclError:
                    pass

            variable.trace_add("write", paint)
            paint()

        if definition.kind == "path":
            def browse() -> None:
                chosen = filedialog.askdirectory(title=definition.label, initialdir=variable.get() or None)
                if chosen:
                    variable.set(chosen)
                    commit()

            self.app._button(holder, "Browse", browse).grid(row=0, column=column, padx=(8, 0))

        def commit(_event=None) -> None:
            if self._commit(definition, variable.get(), error):
                variable.set(str(self.app.settings.get(definition.key)))

        def save_while_typing(_event=None) -> None:
            self._commit(definition, variable.get(), error, quiet=True)

        entry.bind("<KeyRelease>", save_while_typing, add="+")
        entry.bind("<FocusOut>", commit, add="+")
        entry.bind("<Return>", commit, add="+")
        return lambda value: variable.set(str(value))

    def _dropdown(self, parent, variable: tk.StringVar, values, command: Callable[[str], None]) -> tk.OptionMenu:
        app = self.app
        values = list(values)
        dropdown = tk.OptionMenu(parent, variable, *values, command=command)
        dropdown.configure(
            bg=app.c("text_bg"), fg=app.c("text_fg"),
            activebackground=app.c("button_active"), activeforeground=app.c("text_fg"),
            relief=tk.SOLID, bd=1, highlightthickness=1,
            highlightbackground=app.c("border"), highlightcolor=app.c("accent"),
            anchor="w", width=max(8, max((len(v) for v in values), default=8)), cursor="hand2",
        )
        dropdown["menu"].configure(
            bg=app.c("text_bg"), fg=app.c("text_fg"),
            activebackground=app.c("button_active"), activeforeground=app.c("text_fg"),
        )
        app._track(dropdown, "option")
        app._track(dropdown["menu"], "menu")
        return dropdown

    def _control_choice(self, definition, holder, error):
        variable = tk.StringVar(value=str(self.app.settings.get(definition.key)))

        def picked(value: str) -> None:
            if not self._commit(definition, value, error):
                variable.set(str(self.app.settings.get(definition.key)))

        self._dropdown(holder, variable, definition.choices, picked).grid(row=0, column=0, sticky="w")
        return lambda value: variable.set(str(value))

    def _control_list(self, definition, holder, error):
        current = self.app.settings.get(definition.key)
        height = max(3, min(len(current) + 1, 9))
        text = self._plain_text(holder, height=height)
        text.configure(width=46)
        text.grid(row=0, column=0, sticky="w")

        def load(value) -> None:
            text.delete("1.0", tk.END)
            text.insert("1.0", "\n".join(str(item) for item in value))

        def commit(_event=None) -> None:
            if self._commit(definition, text.get("1.0", tk.END), error):
                load(self.app.settings.get(definition.key))

        def save_while_typing(_event=None) -> None:
            self._commit(definition, text.get("1.0", tk.END), error, quiet=True)

        text.bind("<KeyRelease>", save_while_typing, add="+")
        text.bind("<FocusOut>", commit, add="+")
        load(current)
        return load

    def _control_checklist(self, definition, holder, error):
        variables: dict[str, tk.BooleanVar] = {}

        def render(selected) -> None:
            for child in holder.winfo_children():
                child.destroy()
            variables.clear()
            for index, (key, label) in enumerate(known_field_keys(self.app.settings)):
                variable = tk.BooleanVar(value=key in selected)
                variables[key] = variable

                def toggle(k=key) -> None:
                    # Every ticked box, with the clicked one flipped.
                    chosen = [name for name, var in variables.items() if var.get() != (name == k)]
                    if self._commit(definition, self._with_unknown_kept(definition, chosen), error):
                        variables[k].set(not variables[k].get())
                        self.app._refresh_custom_controls()

                self.app._choice_label(holder, label, variable, toggle).grid(
                    row=index // 3, column=index % 3, sticky="w", padx=(0, 18)
                )
            self.app._refresh_custom_controls()

        render(self.app.settings.get(definition.key))
        return render

    def _with_unknown_kept(self, definition: SettingDef, chosen: list[str]) -> list[str]:
        """Keep required keys of currently hidden/removed sections so toggling is lossless."""
        visible = {key for key, _label in known_field_keys(self.app.settings)}
        kept = [k for k in self.app.settings.get(definition.key) if k not in visible]
        return chosen + kept

    def _control_info(self, definition, holder, error):
        label = self.app._label(holder, "", muted=True)
        label.configure(wraplength=620, justify=tk.LEFT)
        label.grid(row=0, column=0, sticky="w")
        self._info_labels[definition.key] = label
        return lambda _value: None

    # ------------------------------------------------------------------
    # Records editor (sections, education, known companies)
    # ------------------------------------------------------------------
    def _control_records(self, definition, holder, error):
        editor = _RecordsEditor(self, holder, definition, error)
        editor.grid(row=0, column=0, sticky="ew")
        return editor.load

    def _new_record(self, definition: SettingDef, rows: list[dict[str, Any]]) -> dict[str, Any]:
        record = {f.key: (list(f.default) if isinstance(f.default, list) else f.default) for f in definition.fields}
        if definition.key == "sections.items":
            taken = {row["key"] for row in rows}
            index = 1
            while f"section_{index}" in taken:
                index += 1
            record.update(key=f"section_{index}", label="New Section", kind="bullets", enabled=True,
                          show_heading=True)
        elif definition.key == "education.entries":
            record.update(label="New Education", enabled=True)
        elif definition.key == "experience.known_companies":
            record.update(name="New Company")
        return record

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------
    def _reset_one(self, key: str) -> None:
        self._rejected.pop(key, None)
        with self.app.settings_edit():
            self.app.settings.reset(key)
        row = self._rows.get(key)
        if row is not None:
            row["error"].configure(text="")
            row["apply"](self.app.settings.get(key))

    def _reset_all(self) -> None:
        if not messagebox.askyesno("Reset All", "Reset every setting to its default value?"):
            return
        with self.app.settings_edit():
            self.app.settings.reset_all()
        self._rebuild_list()

    # ------------------------------------------------------------------
    # settings.json editor
    # ------------------------------------------------------------------
    def _show_json_editor(self) -> None:
        self.list_view.grid_remove()
        self.json_view.grid()
        self._load_json_text()

    def _load_json_text(self) -> None:
        self.json_text.delete("1.0", tk.END)
        self.json_text.insert("1.0", self.app.settings.to_json())
        self.json_error.configure(text="")

    def _save_json(self) -> None:
        try:
            parsed = Settings.from_json(self.json_text.get("1.0", tk.END), defaults=self.app.settings.all_defaults())
        except SettingsError as exc:
            self.json_error.configure(text=str(exc))
            return
        with self.app.settings_edit():
            self.app.settings.replace_all(parsed)
        self._rebuild_list_keep_json()
        if self.app.save_settings_draft():
            self.json_error.configure(text="Saved.", fg=self.app.c("ok_fg"))
        else:
            self.json_error.configure(text="Applied here but not saved to the server yet.")

    def _rebuild_list_keep_json(self) -> None:
        self._rebuild_list()
        self.list_view.grid_remove()
        self.json_view.grid()


class _RecordsEditor(tk.Frame):
    """Editable list of structured rows with add / remove / reorder."""

    def __init__(self, page: SettingsPage, parent, definition: SettingDef, error: tk.Label) -> None:
        super().__init__(parent, bg=page.app.c("panel_bg"))
        self.page = page
        self.app = page.app
        self.definition = definition
        self.error = error
        self._cards: list[dict[str, Any]] = []
        self.columnconfigure(0, weight=1)
        self.load(self.app.settings.get(definition.key))

    # -- rendering ------------------------------------------------------
    def load(self, rows: list[dict[str, Any]]) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._cards = []
        for index, row in enumerate(rows):
            self._build_card(index, row, len(rows))
        add = self.app._button(self, "+ Add", self._add)
        add.grid(row=len(rows), column=0, sticky="w", pady=(6, 0))

    def _build_card(self, index: int, row: dict[str, Any], total: int) -> None:
        app = self.app
        card = app._track(tk.Frame(self, bg=app.c("panel_bg"), padx=8, pady=6, highlightthickness=1,
                                   highlightbackground=app.c("border")), "card")
        card.grid(row=index, column=0, sticky="ew", pady=(0, 6))
        card.columnconfigure(0, weight=1)
        top = app._track(tk.Frame(card, bg=app.c("panel_bg")), "panel_frame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        title = app._label(top, f"{index + 1}.")
        title.grid(row=0, column=0, sticky="w")
        for column, (glyph, action, enabled) in enumerate(
            (("▲", lambda i=index: self._move(i, -1), index > 0),
             ("▼", lambda i=index: self._move(i, 1), index < total - 1),
             ("✕", lambda i=index: self._remove(i), True)),
            start=1,
        ):
            button = app._icon_button(top, glyph, action if enabled else (lambda: None))
            if not enabled:
                button.configure(fg=app.c("muted_fg"), cursor="arrow")
            button.grid(row=0, column=column, padx=2)

        fields_frame = app._track(tk.Frame(card, bg=app.c("panel_bg")), "panel_frame")
        fields_frame.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        widgets: dict[str, Any] = {}
        short = [f for f in self.definition.fields if f.kind in ("str", "int", "choice", "bool")]
        long = [f for f in self.definition.fields if f.kind in ("text", "lines")]
        for position, field_def in enumerate(short):
            cell = app._track(tk.Frame(fields_frame, bg=app.c("panel_bg")), "panel_frame")
            cell.grid(row=position // FIELDS_PER_LINE, column=position % FIELDS_PER_LINE, sticky="w",
                      padx=(0, 12), pady=(0, 4))
            widgets[field_def.key] = self._field_widget(cell, field_def, row.get(field_def.key, field_def.default))
        for offset, field_def in enumerate(long):
            line = (len(short) + FIELDS_PER_LINE - 1) // FIELDS_PER_LINE + offset
            cell = app._track(tk.Frame(fields_frame, bg=app.c("panel_bg")), "panel_frame")
            cell.grid(row=line, column=0, columnspan=FIELDS_PER_LINE, sticky="ew", pady=(0, 4))
            cell.columnconfigure(0, weight=1)
            widgets[field_def.key] = self._field_widget(cell, field_def, row.get(field_def.key, field_def.default))
        self._cards.append(widgets)

    def _field_widget(self, cell: tk.Frame, field_def: FieldDef, value: Any):
        app = self.app
        if field_def.kind == "bool":
            variable = tk.BooleanVar(value=bool(value))

            def toggle() -> None:
                variable.set(not variable.get())
                app._refresh_custom_controls()
                self._commit()

            choice = app._choice_label(cell, field_def.label, variable, toggle)
            choice.grid(row=1, column=0, sticky="w")
            app._refresh_custom_controls()
            return variable
        app._label(cell, field_def.label, muted=True).grid(row=0, column=0, sticky="w")
        if field_def.kind in ("text", "lines"):
            text = self.page._plain_text(cell, height=3 if field_def.kind == "text" else 2)
            text.grid(row=1, column=0, sticky="ew")
            joined = "\n".join(value) if isinstance(value, list) else str(value)
            text.insert("1.0", joined)
            text.bind("<KeyRelease>", lambda _e: self._commit(quiet=True), add="+")
            text.bind("<FocusOut>", lambda _e: self._commit(), add="+")
            return text
        variable = tk.StringVar(value=str(value))
        if field_def.kind == "choice":
            self.page._dropdown(cell, variable, field_def.choices, lambda _v: self._commit()).grid(row=1, column=0, sticky="w")
        else:
            width = 8 if field_def.kind == "int" else field_def.width
            entry = app._entry(cell, variable, width=width)
            entry.grid(row=1, column=0, sticky="w")
            entry.bind("<KeyRelease>", lambda _e: self._commit(quiet=True), add="+")
            entry.bind("<FocusOut>", lambda _e: self._commit(), add="+")
            entry.bind("<Return>", lambda _e: self._commit(), add="+")
        return variable

    # -- reading back ---------------------------------------------------
    def _collect(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for widgets in self._cards:
            row: dict[str, Any] = {}
            for field_def in self.definition.fields:
                widget = widgets[field_def.key]
                if isinstance(widget, tk.Text):
                    text = widget.get("1.0", tk.END)
                    row[field_def.key] = text.splitlines() if field_def.kind == "lines" else text
                else:
                    row[field_def.key] = widget.get()
            rows.append(row)
        return rows

    def _commit(self, rows: Optional[list[dict[str, Any]]] = None, *, quiet: bool = False) -> bool:
        return self.page._commit(
            self.definition, rows if rows is not None else self._collect(), self.error, quiet=quiet
        )

    # -- structural edits -----------------------------------------------
    def _add(self) -> None:
        rows = self._collect()
        rows.append(self.page._new_record(self.definition, rows))
        if self._commit(rows):
            self.load(self.app.settings.get(self.definition.key))

    def _remove(self, index: int) -> None:
        rows = self._collect()
        if self.definition.key == "sections.items":
            name = rows[index].get("label") or rows[index].get("key")
            if not messagebox.askyesno(
                "Remove Section", f"Remove the section '{name}'?\nIts Writer box and resume heading will be gone."
            ):
                return
        del rows[index]
        if self._commit(rows):
            self.load(self.app.settings.get(self.definition.key))

    def _move(self, index: int, offset: int) -> None:
        rows = self._collect()
        target = index + offset
        if not 0 <= target < len(rows):
            return
        rows[index], rows[target] = rows[target], rows[index]
        if self._commit(rows):
            self.load(self.app.settings.get(self.definition.key))
