"""Sign-in and sign-up views for ResumeWriter."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable

from resume_client import ClientError, ResumeClient
from resume_client.local import last_username, remember_username


class AuthView(tk.Frame):
    """Sign In page with a toggle to Sign Up."""

    def __init__(
        self,
        parent,
        *,
        app,
        client: ResumeClient,
        on_authenticated: Callable[[dict], None],
    ) -> None:
        super().__init__(parent, bg=app.c("app_bg"), padx=24, pady=24)
        self.app = app
        self.client = client
        self.on_authenticated = on_authenticated
        self.mode = tk.StringVar(value="signin")

        self.username_var = tk.StringVar(value=last_username(client.config.root))
        self.password_var = tk.StringVar()
        self.confirm_var = tk.StringVar()
        self.display_name_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.status_var = tk.StringVar(value="")
        self.match_var = tk.StringVar(value="")

        self._build()
        self.password_var.trace_add("write", lambda *_args: self._refresh_password_match())
        self.confirm_var.trace_add("write", lambda *_args: self._refresh_password_match())

    def _build(self) -> None:
        card = self.app._track(
            tk.Frame(self, bg=self.app.c("panel_bg"), padx=28, pady=24, highlightthickness=1, highlightbackground=self.app.c("border")),
            "panel_frame",
        )
        card.place(relx=0.5, rely=0.45, anchor="center")

        self.title_label = self.app._label(card, "Sign In")
        self.title_label.configure(font=("Arial", 20, "bold"))
        self.title_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.subtitle_label = self.app._label(card, "Sign in to load your formats and settings.", muted=True)
        self.subtitle_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 16))

        self.app._label(card, "Username").grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.username_entry = self.app._entry(card, self.username_var, width=36)
        self.username_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        self.app._label(card, "Password").grid(row=4, column=0, sticky="w", pady=(0, 4))
        password_entry = self.app._entry(card, self.password_var, width=36)
        self.password_entry = password_entry
        password_entry.configure(show="•")
        password_entry.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        self.confirm_label = self.app._label(card, "Confirm Password")
        self.confirm_entry = self.app._entry(card, self.confirm_var, width=36)
        self.confirm_entry.configure(show="•")
        self.confirm_label.grid(row=6, column=0, sticky="w", pady=(0, 4))
        self.confirm_entry.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        self.match_label = self.app._label(card, "")
        self.match_label.configure(textvariable=self.match_var)
        self.match_label.grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.display_label = self.app._label(card, "Display Name (optional)")
        self.display_entry = self.app._entry(card, self.display_name_var, width=36)
        self.display_label.grid(row=9, column=0, sticky="w", pady=(0, 4))
        self.display_entry.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        self.email_label = self.app._label(card, "Email (optional)")
        self.email_entry = self.app._entry(card, self.email_var, width=36)
        self.email_label.grid(row=11, column=0, sticky="w", pady=(0, 4))
        self.email_entry.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        self.submit_button = self.app._button(card, "Sign In", self._submit, accent=True)
        self.submit_button.grid(row=13, column=0, sticky="w", pady=(8, 8))

        self.switch_button = self.app._button(card, "Need an account? Sign Up", self._toggle_mode)
        self.switch_button.grid(row=13, column=1, sticky="e", pady=(8, 8))

        status = self.app._label(card, "", muted=True)
        status.configure(textvariable=self.status_var)
        status.grid(row=14, column=0, columnspan=2, sticky="w")

        self.status_label = status
        # Enter submits from every field (the shared entry style would move to the next field).
        for entry in (self.username_entry, password_entry, self.confirm_entry, self.display_entry, self.email_entry):
            entry.bind("<Return>", self._on_enter)
            entry.bind("<KP_Enter>", self._on_enter)
        self._apply_mode_visibility()

    def _toggle_mode(self) -> None:
        self.mode.set("signup" if self.mode.get() == "signin" else "signin")
        self.status_var.set("")
        self._apply_mode_visibility()

    def _apply_mode_visibility(self) -> None:
        signup = self.mode.get() == "signup"
        self.title_label.configure(text="Sign Up" if signup else "Sign In")
        self.subtitle_label.configure(
            text="Create a local account to save formats and settings."
            if signup
            else "Sign in to load your formats and settings."
        )
        self.submit_button.configure(text="Create Account" if signup else "Sign In")
        self.submit_button.normal_text = self.submit_button.cget("text")
        self.switch_button.configure(
            text="Already have an account? Sign In" if signup else "Need an account? Sign Up"
        )
        self.switch_button.normal_text = self.switch_button.cget("text")

        for widget in (
            self.confirm_label,
            self.confirm_entry,
            self.match_label,
            self.display_label,
            self.display_entry,
            self.email_label,
            self.email_entry,
        ):
            if signup:
                widget.grid()
            else:
                widget.grid_remove()
        self._refresh_password_match()

    def _refresh_password_match(self) -> None:
        if self.mode.get() != "signup":
            self.match_var.set("")
            return
        password = self.password_var.get()
        confirm = self.confirm_var.get()
        if not confirm:
            self.match_var.set("")
            return
        if password == confirm:
            self.match_var.set("Passwords match")
            self.match_label.configure(fg=self.app.c("ok_fg"))
        else:
            self.match_var.set("Passwords do not match")
            self.match_label.configure(fg=self.app.c("error_fg"))

    def _on_enter(self, _event=None) -> str:
        self._submit()
        return "break"

    def _submit(self) -> None:
        username = self.username_var.get().strip()
        password = self.password_var.get()
        try:
            if self.mode.get() == "signup":
                if password != self.confirm_var.get():
                    raise ClientError("Passwords do not match")
                profile = self.client.signup(
                    username,
                    password,
                    display_name=self.display_name_var.get().strip(),
                    email=self.email_var.get().strip(),
                )
            else:
                profile = self.client.login(username, password)
        except ClientError as exc:
            self.status_var.set(str(exc))
            self.status_label.configure(fg=self.app.c("error_fg"))
            return
        except Exception as exc:
            messagebox.showerror("Authentication failed", str(exc))
            return

        self.status_var.set("")
        remember_username(self.client.config.root, username)
        # Keep the username and password so signing in again is one click (or one Enter).
        self.clear_form(mode="signin", keep_credentials=True)
        self.on_authenticated(profile)

    def clear_form(self, *, mode: str = "signin", keep_credentials: bool = False) -> None:
        """Reset the form and show Sign In (or Sign Up). Credentials stay when ``keep_credentials`` is set."""
        self.mode.set(mode)
        if not keep_credentials:
            self.username_var.set("")
            self.password_var.set("")
        self.confirm_var.set("")
        self.display_name_var.set("")
        self.email_var.set("")
        self.status_var.set("")
        self.match_var.set("")
        self._apply_mode_visibility()

    def focus_username(self) -> None:
        """Focus the first field that still needs input (the password when the username is remembered)."""
        if self.username_var.get().strip():
            self.password_entry.focus_set()
        else:
            self.username_entry.focus_set()
