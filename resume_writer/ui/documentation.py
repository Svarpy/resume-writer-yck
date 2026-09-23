"""Documentation page showing only the How To Use section."""

from __future__ import annotations

import tkinter as tk

from resume_writer.docs.loader import load_how_to_use_section


class DocumentationPage(tk.Frame):
    def __init__(self, parent, *, app) -> None:
        super().__init__(parent, bg=app.c("app_bg"), padx=16, pady=16)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        title = self.app._label(self, "How To Use The Application")
        title.configure(font=("Arial", 16, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 8))

        body_frame = self.app._section(self, "Guide")
        body_frame.grid(row=1, column=0, sticky="nsew")
        body_frame.columnconfigure(0, weight=1)
        body_frame.rowconfigure(0, weight=1)

        self.text = self.app._text_widget(body_frame, height=24)
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.configure(wrap=tk.WORD, state=tk.NORMAL)
        # Documentation text should not trigger writer validation.
        self.text.unbind("<KeyRelease>")
        self.text.unbind("<FocusOut>")
        self.refresh()

    def refresh(self) -> None:
        content = load_how_to_use_section()
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self.text.configure(state=tk.DISABLED)
