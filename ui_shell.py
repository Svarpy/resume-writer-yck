"""Collapsible left sidebar and page navigation shell."""

from __future__ import annotations

import tkinter as tk
from typing import Callable


SIDEBAR_EXPAND_WIDTH = 1000
SIDEBAR_EXPANDED_PX = 200
SIDEBAR_COLLAPSED_PX = 52

NAV_ITEMS = (
    ("writer", "Writer"),
    ("formatter", "Formatter"),
    ("settings", "Settings"),
    ("documentation", "Documentation"),
)


class AppShell(tk.Frame):
    """Left sidebar + page container around the existing writer UI."""

    def __init__(
        self,
        parent,
        *,
        app,
        on_logout: Callable[[], None],
        on_navigate: Callable[[str], None],
    ) -> None:
        super().__init__(parent, bg=app.c("app_bg"))
        self.app = app
        self.on_logout = on_logout
        self.on_navigate = on_navigate
        self.expanded = tk.BooleanVar(value=True)
        self.active_page = tk.StringVar(value="writer")
        self._nav_buttons: dict[str, tk.Label] = {}

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = self.app._track(
            tk.Frame(self, bg=self.app.c("panel_bg"), width=SIDEBAR_EXPANDED_PX, highlightthickness=1, highlightbackground=self.app.c("border")),
            "panel_frame",
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        self.content = self.app._track(tk.Frame(self, bg=self.app.c("app_bg")), "app_frame")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self._build_sidebar()
        self.bind_all("<Configure>", self._on_root_configure, add="+")

    def _build_sidebar(self) -> None:
        top = self.app._track(tk.Frame(self.sidebar, bg=self.app.c("panel_bg"), padx=8, pady=10), "panel_frame")
        top.pack(fill=tk.X)

        self.menu_button = self.app._icon_button(top, "☰", self.toggle_sidebar)
        self.menu_button.configure(font=("Arial", 16, "bold"))
        self.menu_button.pack(side=tk.LEFT)

        self.brand_label = self.app._label(top, "Resume Writer")
        self.brand_label.configure(font=("Arial", 12, "bold"))
        self.brand_label.pack(side=tk.LEFT, padx=(8, 0))

        self.logout_button = self.app._button(self.sidebar, "Sign Out", self.on_logout)
        self.logout_button.pack(fill=tk.X, padx=8, pady=(4, 12))

        self.user_label = self.app._label(self.sidebar, "", muted=True)
        self.user_label.pack(fill=tk.X, padx=12, pady=(0, 8))

        nav = self.app._track(tk.Frame(self.sidebar, bg=self.app.c("panel_bg")), "panel_frame")
        nav.pack(fill=tk.BOTH, expand=True, padx=4)

        for key, title in NAV_ITEMS:
            button = self.app._button(nav, title, lambda k=key: self.navigate(k))
            button.pack(fill=tk.X, padx=4, pady=3)
            button.nav_key = key
            self._nav_buttons[key] = button

        self._refresh_nav_styles()

    def set_username(self, username: str) -> None:
        self.user_label.configure(text=f"Signed in as {username}")

    def navigate(self, page_key: str) -> None:
        if page_key not in self._nav_buttons:
            return
        self.active_page.set(page_key)
        self._refresh_nav_styles()
        self.on_navigate(page_key)

    def set_expanded(self, expanded: bool) -> None:
        self.expanded.set(bool(expanded))
        width = SIDEBAR_EXPANDED_PX if expanded else SIDEBAR_COLLAPSED_PX
        self.sidebar.configure(width=width)
        if expanded:
            self.brand_label.pack(side=tk.LEFT, padx=(8, 0))
            self.logout_button.pack(fill=tk.X, padx=8, pady=(4, 12))
            self.user_label.pack(fill=tk.X, padx=12, pady=(0, 8))
            for key, title in NAV_ITEMS:
                self._nav_buttons[key].configure(text=title)
                self._nav_buttons[key].normal_text = title
        else:
            self.brand_label.pack_forget()
            self.logout_button.pack_forget()
            self.user_label.pack_forget()
            icons = {
                "writer": "✍",
                "formatter": "▦",
                "settings": "⚙",
                "documentation": "?",
            }
            for key, button in self._nav_buttons.items():
                label = icons.get(key, "•")
                button.configure(text=label)
                button.normal_text = label
        self._refresh_nav_styles()

    def apply_default_collapse_for_width(self, width: int) -> None:
        self.set_expanded(width >= SIDEBAR_EXPAND_WIDTH)

    def _on_root_configure(self, event) -> None:
        # Only react to the root window size; ignore child widget noise.
        if event.widget is not self.app:
            return
        # Do not fight the user after they manually toggle; only set initial default once.
        if getattr(self, "_user_toggled", False):
            return
        if not getattr(self, "_initial_sized", False):
            self.apply_default_collapse_for_width(event.width)
            self._initial_sized = True

    def toggle_sidebar(self) -> None:  # noqa: F811 — intentional override with user flag
        self._user_toggled = True
        self.set_expanded(not self.expanded.get())

    def _refresh_nav_styles(self) -> None:
        active = self.active_page.get()
        for key, button in self._nav_buttons.items():
            if key == active:
                button.configure(
                    bg=self.app.c("accent"),
                    fg="#ffffff",
                    activebackground=self.app.c("accent"),
                    activeforeground="#ffffff",
                )
            else:
                button.configure(
                    bg=self.app.c("button_bg"),
                    fg=self.app.c("text_fg"),
                    activebackground=self.app.c("button_active"),
                    activeforeground=self.app.c("text_fg"),
                )
