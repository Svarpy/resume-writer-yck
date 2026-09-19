"""Formatter page: primary format selection and saved-format CRUD."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import formats_store
import user_auth


class FormatterPage(tk.Frame):
    def __init__(
        self,
        parent,
        *,
        app,
        on_primary_changed: Optional[Callable[[formats_store.ResumeFormatSpec], None]] = None,
    ) -> None:
        super().__init__(parent, bg=app.c("app_bg"), padx=16, pady=16)
        self.app = app
        self.on_primary_changed = on_primary_changed
        self.primary_var = tk.StringVar(value=formats_store.DEFAULT_FORMAT_ID)
        self._format_rows: list[tk.Frame] = []
        self._specs: list[formats_store.ResumeFormatSpec] = []
        self._name_by_id: dict[str, str] = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build()

    def _build(self) -> None:
        header = self.app._section(self, "Primary Format")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        self.app._label(header, "Used by Writer when generating resumes").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        self.app._label(header, "Primary").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.primary_menu = tk.OptionMenu(header, self.primary_var, formats_store.DEFAULT_FORMAT_ID)
        self._style_option_menu(self.primary_menu)
        self.primary_menu.grid(row=1, column=1, sticky="ew")
        self.app._button(header, "Set Primary", self._set_primary).grid(row=1, column=2, padx=(8, 0))

        actions = self.app._section(self, "Formats")
        actions.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.app._button(actions, "Add Format", self._add_format, accent=True).pack(side=tk.LEFT)

        list_section = self.app._section(self, "Saved Formats")
        list_section.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        list_section.columnconfigure(0, weight=1)
        list_section.rowconfigure(0, weight=1)

        canvas_host = self.app._track(tk.Frame(list_section, bg=self.app.c("panel_bg")), "panel_frame")
        canvas_host.grid(row=0, column=0, sticky="nsew")
        canvas_host.columnconfigure(0, weight=1)
        canvas_host.rowconfigure(0, weight=1)

        self.list_canvas = tk.Canvas(canvas_host, bg=self.app.c("panel_bg"), highlightthickness=0)
        self.app._track(self.list_canvas, "panel_frame")
        scrollbar = tk.Scrollbar(canvas_host, orient=tk.VERTICAL, command=self.list_canvas.yview)
        self.list_canvas.configure(yscrollcommand=scrollbar.set)
        self.list_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.list_frame = self.app._track(tk.Frame(self.list_canvas, bg=self.app.c("panel_bg")), "panel_frame")
        self._list_window = self.list_canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", self._on_list_configure)
        self.list_canvas.bind("<Configure>", self._on_canvas_configure)

    def _style_option_menu(self, dropdown: tk.OptionMenu) -> None:
        dropdown.configure(
            bg=self.app.c("text_bg"),
            fg=self.app.c("text_fg"),
            activebackground=self.app.c("button_active"),
            activeforeground=self.app.c("text_fg"),
            relief=tk.SOLID,
            bd=1,
            highlightthickness=1,
            highlightbackground=self.app.c("border"),
            highlightcolor=self.app.c("accent"),
            anchor="w",
            width=28,
            cursor="hand2",
        )
        dropdown["menu"].configure(
            bg=self.app.c("text_bg"),
            fg=self.app.c("text_fg"),
            activebackground=self.app.c("button_active"),
            activeforeground=self.app.c("text_fg"),
        )
        self.app._track(dropdown, "option")
        self.app._track(dropdown["menu"], "menu")

    def _on_list_configure(self, _event=None) -> None:
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.list_canvas.itemconfigure(self._list_window, width=event.width)

    def _username(self) -> str:
        return user_auth.require_current_user()

    def refresh(self) -> None:
        try:
            username = self._username()
            self._specs = formats_store.list_formats(username)
            primary = formats_store.get_primary_format(username)
            self.primary_var.set(primary.id)
        except Exception as exc:
            messagebox.showerror("Formatter", str(exc))
            return

        self._name_by_id = {spec.id: spec.name for spec in self._specs}
        menu = self.primary_menu["menu"]
        menu.delete(0, tk.END)
        for spec in self._specs:
            label = f"{spec.name} ({spec.id})"
            menu.add_command(label=label, command=lambda value=spec.id: self.primary_var.set(value))

        for row in self._format_rows:
            row.destroy()
        self._format_rows.clear()

        for index, spec in enumerate(self._specs):
            row = self.app._track(tk.Frame(self.list_frame, bg=self.app.c("panel_bg"), pady=6), "panel_frame")
            row.grid(row=index, column=0, sticky="ew")
            row.columnconfigure(0, weight=1)
            title = spec.name
            if spec.protected:
                title = f"{title} (protected)"
            detail = (
                f"{title}\n"
                f"Font {spec.font_name} · Name {spec.name_size} · "
                f"Heading {spec.heading_size} · Body {spec.body_size}"
            )
            label = self.app._label(row, detail)
            label.grid(row=0, column=0, sticky="w")
            if not spec.protected:
                self.app._button(row, "Delete", lambda s=spec: self._delete_format(s)).grid(
                    row=0, column=1, padx=(8, 4)
                )
            else:
                locked = self.app._label(row, "Locked", muted=True)
                locked.grid(row=0, column=1, sticky="e", padx=(8, 4))
            self._format_rows.append(row)

    def _set_primary(self) -> None:
        format_id = self.primary_var.get().strip() or formats_store.DEFAULT_FORMAT_ID
        try:
            spec = formats_store.set_primary_format(self._username(), format_id)
        except formats_store.FormatError as exc:
            messagebox.showerror("Primary format", str(exc))
            return
        if self.on_primary_changed:
            self.on_primary_changed(spec)
        messagebox.showinfo("Primary format", f"Primary format set to:\n{spec.name}")

    def _ask_format_name(self, initial: str = "") -> Optional[str]:
        """Themed name dialog with readable Cancel/Save text buttons (no glyph icons)."""
        dialog = tk.Toplevel(self)
        dialog.title("Format name")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        dialog.configure(bg=self.app.c("panel_bg"))
        dialog.grab_set()

        result: dict[str, Optional[str]] = {"value": None}
        name_var = tk.StringVar(value=initial)

        body = self.app._track(
            tk.Frame(dialog, bg=self.app.c("panel_bg"), padx=20, pady=16),
            "panel_frame",
        )
        body.pack(fill=tk.BOTH, expand=True)

        self.app._label(body, "Name for this format:").pack(anchor="w", pady=(0, 8))
        entry = self.app._entry(body, name_var, width=36)
        entry.pack(fill=tk.X, pady=(0, 16))
        entry.focus_set()
        entry.selection_range(0, tk.END)

        buttons = self.app._track(tk.Frame(body, bg=self.app.c("panel_bg")), "panel_frame")
        buttons.pack(fill=tk.X)

        def _cancel() -> None:
            result["value"] = None
            dialog.destroy()

        def _save() -> None:
            result["value"] = name_var.get()
            dialog.destroy()

        # Explicit text labels — avoid Tk glyph/icon buttons that render as dots on macOS.
        cancel_btn = self.app._button(buttons, "Cancel", _cancel)
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))
        save_btn = self.app._button(buttons, "Save", _save, accent=True)
        save_btn.pack(side=tk.RIGHT)

        dialog.bind("<Return>", lambda _event: _save())
        dialog.bind("<Escape>", lambda _event: _cancel())
        dialog.protocol("WM_DELETE_WINDOW", _cancel)

        dialog.update_idletasks()
        parent = self.winfo_toplevel()
        x = parent.winfo_rootx() + max(40, (parent.winfo_width() - dialog.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(40, (parent.winfo_height() - dialog.winfo_reqheight()) // 3)
        dialog.geometry(f"+{x}+{y}")

        self.wait_window(dialog)
        if hasattr(self.app, "_prune_tracked_widgets"):
            self.app._prune_tracked_widgets()
            self.app._apply_button_state()
        return result["value"]

    def _add_format(self) -> None:
        path = filedialog.askopenfilename(
            title="Upload Word document",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
        )
        if not path:
            return
        name = self._ask_format_name()
        if name is None:
            return
        if not name.strip():
            messagebox.showwarning("Add Format", "Please enter a format name.", parent=self)
            return
        try:
            spec = formats_store.add_format_from_docx(self._username(), path, name.strip())
        except formats_store.FormatError as exc:
            messagebox.showerror("Add Format", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Add Format", str(exc))
            return
        self.refresh()
        messagebox.showinfo("Add Format", f"Saved format:\n{spec.name}")

    def _delete_format(self, spec: formats_store.ResumeFormatSpec) -> None:
        if spec.protected:
            messagebox.showwarning("Delete Format", "The default application format cannot be deleted.")
            return
        if not messagebox.askyesno("Delete Format", f"Delete format '{spec.name}'?", parent=self):
            return
        try:
            formats_store.delete_format(self._username(), spec.id)
        except formats_store.FormatError as exc:
            messagebox.showerror("Delete Format", str(exc))
            return
        self.refresh()
        if self.on_primary_changed:
            try:
                self.on_primary_changed(formats_store.get_primary_format(self._username()))
            except Exception:
                pass
