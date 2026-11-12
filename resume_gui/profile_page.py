"""Profile page: account details, password change and access tokens (for the MCP server)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from resume_client import ClientError


class ProfilePage(tk.Frame):
    def __init__(self, parent, *, app) -> None:
        super().__init__(parent, bg=app.c("app_bg"), padx=16, pady=16)
        self.app = app

        self.username_var = tk.StringVar()
        self.display_name_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.old_password_var = tk.StringVar()
        self.new_password_var = tk.StringVar()
        self.token_name_var = tk.StringVar(value="Claude")
        self._token_rows: list[tk.Widget] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg=app.c("app_bg"), highlightthickness=0, bd=0)
        app._track(self.canvas, "canvas")
        scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.body = app._track(tk.Frame(self.canvas, bg=app.c("app_bg")), "app_frame")
        self._body_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._body_window, width=e.width))
        self.body.columnconfigure(0, weight=1)
        self._build()

    def scroll_target(self):
        """What the app-wide wheel/trackpad handler scrolls on this page."""
        return self.canvas

    @property
    def client(self):
        return self.app.client

    def _build(self) -> None:
        title = self.app._label(self.body, "Profile")
        title.configure(font=("Arial", 16, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 8))

        profile = self.app._section(self.body, "Account")
        profile.grid(row=1, column=0, sticky="ew")
        profile.columnconfigure(1, weight=1)

        self.app._label(profile, "Username").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        username_entry = self.app._entry(profile, self.username_var, width=36)
        username_entry.configure(state="readonly")
        username_entry.grid(row=0, column=1, sticky="w", pady=(0, 8))

        self.app._label(profile, "Display Name").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.app._entry(profile, self.display_name_var, width=36).grid(row=1, column=1, sticky="w", pady=(0, 8))

        self.app._label(profile, "Email").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.app._entry(profile, self.email_var, width=36).grid(row=2, column=1, sticky="w", pady=(0, 8))

        self.app._label(
            profile,
            "Resume header details (name, email, phone, location) are edited in Settings > Personal Details.",
            muted=True,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.app._button(profile, "Save Profile", self._save_profile, accent=True).grid(
            row=4, column=1, sticky="w", pady=(4, 0)
        )

        password = self.app._section(self.body, "Change Password")
        password.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        password.columnconfigure(1, weight=1)

        self.app._label(password, "Current Password").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        old_entry = self.app._entry(password, self.old_password_var, width=36)
        old_entry.configure(show="•")
        old_entry.grid(row=0, column=1, sticky="w", pady=(0, 8))

        self.app._label(password, "New Password").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        new_entry = self.app._entry(password, self.new_password_var, width=36)
        new_entry.configure(show="•")
        new_entry.grid(row=1, column=1, sticky="w", pady=(0, 8))

        self.app._button(password, "Update Password", self._change_password).grid(
            row=2, column=1, sticky="w", pady=(4, 0)
        )

        self.tokens_section = self.app._section(self.body, "Access Tokens (for Claude and other MCP apps)")
        self.tokens_section.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.tokens_section.columnconfigure(1, weight=1)
        self.app._label(
            self.tokens_section,
            "Put a token in RW_API_TOKEN so the MCP server can use your account. A token is shown only once.",
            muted=True,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.app._label(self.tokens_section, "Name").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.app._entry(self.tokens_section, self.token_name_var, width=24).grid(row=1, column=1, sticky="w")
        self.app._button(self.tokens_section, "Create Token", self._create_token).grid(row=1, column=2, padx=(8, 0))
        self.tokens_list = self.app._track(tk.Frame(self.tokens_section, bg=self.app.c("panel_bg")), "panel_frame")
        self.tokens_list.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.app._label(
            self.tokens_section,
            "Interactive API documentation (Swagger): open it, click Authorize and paste a token to try the API.",
            muted=True,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 4))
        self.app._button(self.tokens_section, "Open API Documentation", self.app.open_api_docs).grid(
            row=4, column=0, columnspan=3, sticky="w"
        )

    def refresh(self) -> None:
        try:
            profile = self.client.profile()
        except ClientError as exc:
            messagebox.showerror("Profile", str(exc))
            return
        self.username_var.set(profile["username"])
        self.display_name_var.set(profile["display_name"])
        self.email_var.set(profile["email"])
        self.old_password_var.set("")
        self.new_password_var.set("")
        self._refresh_tokens()

    def _refresh_tokens(self) -> None:
        for row in self._token_rows:
            row.destroy()
        self._token_rows.clear()
        try:
            tokens = self.client.list_tokens()
        except ClientError:
            return
        for index, token in enumerate(tokens):
            row = self.app._track(tk.Frame(self.tokens_list, bg=self.app.c("panel_bg")), "panel_frame")
            row.grid(row=index, column=0, sticky="ew", pady=2)
            used = token["last_used_at"] or "never used"
            self.app._label(row, f"{token['name']}   ({token['prefix']}…, {used})").grid(row=0, column=0, sticky="w")
            self.app._button(row, "Revoke", lambda t=token: self._revoke_token(t)).grid(row=0, column=1, padx=(12, 0))
            self._token_rows.append(row)
        self.app._prune_tracked_widgets()

    def _save_profile(self) -> None:
        try:
            self.client.update_profile(self.display_name_var.get(), self.email_var.get())
        except ClientError as exc:
            messagebox.showerror("Save Profile", str(exc))
            return
        if hasattr(self.app, "_refresh_sidebar_user_label"):
            self.app._refresh_sidebar_user_label()
        messagebox.showinfo("Save Profile", "Profile updated.")

    def _change_password(self) -> None:
        try:
            self.client.change_password(self.old_password_var.get(), self.new_password_var.get())
        except ClientError as exc:
            messagebox.showerror("Change Password", str(exc))
            return
        self.old_password_var.set("")
        self.new_password_var.set("")
        messagebox.showinfo("Change Password", "Password updated.")

    def _create_token(self) -> None:
        try:
            created = self.client.create_token(self.token_name_var.get())
        except ClientError as exc:
            messagebox.showerror("Create Token", str(exc))
            return
        self.clipboard_clear()
        self.clipboard_append(created["token"])
        messagebox.showinfo(
            "Access token created",
            f"{created['token']}\n\nIt has been copied to the clipboard. Store it as RW_API_TOKEN; "
            "it cannot be shown again.",
        )
        self._refresh_tokens()

    def _revoke_token(self, token: dict) -> None:
        if not messagebox.askyesno("Revoke Token", f"Revoke '{token['name']}'? Apps using it will stop working."):
            return
        try:
            self.client.revoke_token(token["id"])
        except ClientError as exc:
            messagebox.showerror("Revoke Token", str(exc))
            return
        self._refresh_tokens()
