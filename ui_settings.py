"""Settings page: profile, password change, and dark mode."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable

import user_auth


class SettingsPage(tk.Frame):
    def __init__(
        self,
        parent,
        *,
        app,
        on_theme_toggle: Callable[[], None],
    ) -> None:
        super().__init__(parent, bg=app.c("app_bg"), padx=16, pady=16)
        self.app = app
        self.on_theme_toggle = on_theme_toggle

        self.username_var = tk.StringVar()
        self.display_name_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.old_password_var = tk.StringVar()
        self.new_password_var = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        profile = self.app._section(self, "Profile")
        profile.grid(row=0, column=0, sticky="ew")
        profile.columnconfigure(1, weight=1)

        self.app._label(profile, "Username").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        username_entry = self.app._entry(profile, self.username_var, width=36)
        username_entry.configure(state="readonly")
        username_entry.grid(row=0, column=1, sticky="w", pady=(0, 8))

        self.app._label(profile, "Display Name").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.app._entry(profile, self.display_name_var, width=36).grid(row=1, column=1, sticky="w", pady=(0, 8))

        self.app._label(profile, "Email").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.app._entry(profile, self.email_var, width=36).grid(row=2, column=1, sticky="w", pady=(0, 8))

        self.app._button(profile, "Save Profile", self._save_profile, accent=True).grid(
            row=3, column=1, sticky="w", pady=(4, 0)
        )

        appearance = self.app._section(self, "Appearance")
        appearance.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.app._label(appearance, "Theme").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.app.theme_toggle = self.app._toggle_button(appearance, self.app.dark_mode_var, self._toggle_theme)
        self.app.theme_toggle.grid(row=0, column=1, sticky="w")
        self.app._draw_theme_toggle()

        password = self.app._section(self, "Change Password")
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

    def refresh(self) -> None:
        try:
            profile = user_auth.get_current_profile()
        except user_auth.AuthError as exc:
            messagebox.showerror("Settings", str(exc))
            return
        self.username_var.set(profile.username)
        self.display_name_var.set(profile.display_name)
        self.email_var.set(profile.email)
        if bool(profile.dark_mode) != bool(self.app.dark_mode_var.get()):
            self.app.dark_mode_var.set(bool(profile.dark_mode))
            self.app._configure_style()
            self.app._apply_theme()
        self.app._refresh_custom_controls()

    def _toggle_theme(self) -> None:
        self.on_theme_toggle()
        username = user_auth.get_current_user()
        if username:
            try:
                user_auth.update_profile(username, dark_mode=bool(self.app.dark_mode_var.get()))
            except user_auth.AuthError:
                pass

    def _save_profile(self) -> None:
        try:
            username = user_auth.require_current_user()
            user_auth.update_profile(
                username,
                display_name=self.display_name_var.get(),
                email=self.email_var.get(),
            )
        except user_auth.AuthError as exc:
            messagebox.showerror("Save Profile", str(exc))
            return
        if hasattr(self.app, "_refresh_sidebar_user_label"):
            self.app._refresh_sidebar_user_label()
        messagebox.showinfo("Save Profile", "Profile updated.")

    def _change_password(self) -> None:
        try:
            username = user_auth.require_current_user()
            user_auth.change_password(
                username,
                self.old_password_var.get(),
                self.new_password_var.get(),
            )
        except user_auth.AuthError as exc:
            messagebox.showerror("Change Password", str(exc))
            return
        self.old_password_var.set("")
        self.new_password_var.set("")
        messagebox.showinfo("Change Password", "Password updated.")
