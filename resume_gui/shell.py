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
)
PROFILE_KEY = "profile"
PROFILE_TITLE = "Profile"
PROFILE_FALLBACK_ICON = "P"

# Simple ASCII glyphs render cleanly on macOS Tk (avoid soft emoji).
COLLAPSED_NAV_ICONS = {
    "writer": "W",
    "formatter": "F",
    "settings": "S",
}
LOGOUT_ICON = "↪"
COLLAPSED_ICON_FONT = ("Arial", 17, "bold")
EXPANDED_NAV_FONT = ("Arial", 12)
MENU_ICON_FONT = ("Arial", 18, "bold")


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
        self.menu_button.configure(font=MENU_ICON_FONT, relief=tk.FLAT, bd=0, highlightthickness=0)
        self.menu_button.pack(side=tk.LEFT)

        self.brand_label = self.app._label(top, "Resume Writer")
        self.brand_label.configure(font=("Arial", 12, "bold"))
        self.brand_label.pack(side=tk.LEFT, padx=(8, 0))

        # Bottom chrome first so Sign Out stays at the foot (expanded + collapsed).
        self.bottom = self.app._track(
            tk.Frame(self.sidebar, bg=self.app.c("panel_bg")),
            "panel_frame",
        )
        self.bottom.pack(side=tk.BOTTOM, fill=tk.X)

        self.logout_button = self.app._button(self.bottom, "Sign Out", self.on_logout)
        self.logout_button.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 12))

        # Profile sits directly above Sign Out: a "Profile" button when expanded,
        # a person icon (falling back to the letter P) when collapsed.
        self.profile_button = self.app._button(self.bottom, PROFILE_TITLE, lambda: self.navigate(PROFILE_KEY))
        self.profile_button.nav_key = PROFILE_KEY
        self.profile_button.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 0))
        self._profile_icons: dict[tuple[str, str], tk.PhotoImage] = {}

        self.user_label = self.app._label(self.bottom, "", muted=True)
        self.user_label.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 4))

        nav = self.app._track(tk.Frame(self.sidebar, bg=self.app.c("panel_bg")), "panel_frame")
        nav.pack(fill=tk.BOTH, expand=True, padx=4)

        for key, title in NAV_ITEMS:
            button = self.app._button(nav, title, lambda k=key: self.navigate(k))
            button.pack(fill=tk.X, padx=4, pady=3)
            button.nav_key = key
            self._nav_buttons[key] = button

        self._refresh_nav_styles()

    def set_signed_in_label(self, display_name: str = "", username: str = "") -> None:
        """Prefer display name; fall back to username when display name is empty."""
        label = (display_name or "").strip() or (username or "").strip() or "user"
        self.user_label.configure(text=f"Signed in as {label}")

    def set_username(self, username: str) -> None:
        # Backward-compatible alias; prefer set_signed_in_label when profile is available.
        self.set_signed_in_label(username=username)

    def navigate(self, page_key: str) -> None:
        if page_key not in self._nav_buttons and page_key != PROFILE_KEY:
            return
        if page_key != self.active_page.get() and not self.app.confirm_leave_settings():
            return                                  # unsaved Settings and the user chose to stay
        self.active_page.set(page_key)
        self._refresh_nav_styles()
        self.on_navigate(page_key)

    def set_expanded(self, expanded: bool) -> None:
        self.expanded.set(bool(expanded))
        width = SIDEBAR_EXPANDED_PX if expanded else SIDEBAR_COLLAPSED_PX
        self.sidebar.configure(width=width)
        if expanded:
            self.brand_label.pack(side=tk.LEFT, padx=(8, 0))
            self.logout_button.configure(text="Sign Out")
            self.logout_button.normal_text = "Sign Out"
            # Pack side=BOTTOM first so logout stays under the user label.
            self.logout_button.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 12))
            self.profile_button.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 0))
            self.user_label.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 4))
            for key, title in NAV_ITEMS:
                self._nav_buttons[key].configure(text=title)
                self._nav_buttons[key].normal_text = title
        else:
            self.brand_label.pack_forget()
            self.user_label.pack_forget()
            # Collapsed: ↪ icon remains packed at the bottom of the sidebar.
            self.logout_button.configure(text=LOGOUT_ICON)
            self.logout_button.normal_text = LOGOUT_ICON
            self.logout_button.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(4, 12))
            self.profile_button.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(4, 0))
            for key, button in self._nav_buttons.items():
                label = COLLAPSED_NAV_ICONS.get(key, "•")
                button.configure(text=label)
                button.normal_text = label
        self._refresh_nav_styles()

    def apply_default_collapse_for_width(self, width: int) -> None:
        """Initial expanded/collapsed state from Settings > Appearance."""
        settings = getattr(self.app, "settings", None)
        mode, threshold = "auto", SIDEBAR_EXPAND_WIDTH
        if settings is not None:
            mode = settings.get("appearance.sidebar_mode")
            threshold = settings.get("appearance.sidebar_auto_collapse_width")
        if mode == "expanded":
            self.set_expanded(True)
        elif mode == "collapsed":
            self.set_expanded(False)
        else:
            self.set_expanded(width >= threshold)

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

    def toggle_sidebar(self) -> None:
        self._user_toggled = True
        self.set_expanded(not self.expanded.get())

    def _refresh_nav_styles(self) -> None:
        active = self.active_page.get()
        collapsed = not self.expanded.get()
        panel_bg = self.app.c("panel_bg")
        text_fg = self.app.c("text_fg")
        accent = self.app.c("accent")

        # Keep hamburger crisp in both modes.
        try:
            self.menu_button.configure(
                font=MENU_ICON_FONT,
                relief=tk.FLAT,
                bd=0,
                highlightthickness=0,
                bg=panel_bg,
                fg=accent,
            )
        except tk.TclError:
            pass

        for key, button in self._nav_buttons.items():
            is_active = key == active
            if collapsed:
                button.configure(
                    relief=tk.FLAT,
                    bd=0,
                    highlightthickness=0,
                    padx=2,
                    pady=8,
                    font=COLLAPSED_ICON_FONT,
                    bg=panel_bg,
                    fg=accent if is_active else text_fg,
                    activebackground=panel_bg,
                    activeforeground=accent if is_active else text_fg,
                )
            elif is_active:
                button.configure(
                    relief=tk.RAISED,
                    bd=1,
                    padx=10,
                    pady=5,
                    font=EXPANDED_NAV_FONT,
                    bg=accent,
                    fg="#ffffff",
                    activebackground=accent,
                    activeforeground="#ffffff",
                )
            else:
                button.configure(
                    relief=tk.RAISED,
                    bd=1,
                    padx=10,
                    pady=5,
                    font=EXPANDED_NAV_FONT,
                    bg=self.app.c("button_bg"),
                    fg=text_fg,
                    activebackground=self.app.c("button_active"),
                    activeforeground=text_fg,
                )

        self._style_profile_button(collapsed, active == PROFILE_KEY)

        # Sign Out: text button when expanded; flat icon when collapsed (same pack slot).
        try:
            if collapsed:
                self.logout_button.configure(
                    relief=tk.FLAT,
                    bd=0,
                    highlightthickness=0,
                    padx=2,
                    pady=6,
                    font=COLLAPSED_ICON_FONT,
                    bg=panel_bg,
                    fg=text_fg,
                    activebackground=panel_bg,
                    activeforeground=text_fg,
                )
            else:
                self.logout_button.configure(
                    relief=tk.RAISED,
                    bd=1,
                    padx=10,
                    pady=5,
                    font=EXPANDED_NAV_FONT,
                    bg=self.app.c("button_bg"),
                    fg=text_fg,
                    activebackground=self.app.c("button_active"),
                    activeforeground=text_fg,
                )
        except tk.TclError:
            pass

    # -- profile button ---------------------------------------------------
    def _person_icon(self, fg: str, bg: str, size: int = 24) -> tk.PhotoImage:
        """A small head-and-shoulders icon drawn pixel by pixel (no image files, no emoji)."""
        key = (fg, bg)
        cached = self._profile_icons.get(key)
        if cached is not None:
            return cached
        image = tk.PhotoImage(master=self.app, width=size, height=size)
        centre = (size - 1) / 2
        head_y, head_r = size * 0.32, size * 0.21
        body_y, body_r = size - 0.5, size * 0.40
        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                in_head = (x - centre) ** 2 + (y - head_y) ** 2 <= head_r ** 2
                in_body = y <= body_y and ((x - centre) / body_r) ** 2 + ((y - body_y) / body_r) ** 2 <= 1
                row.append(fg if in_head or in_body else bg)
            rows.append("{" + " ".join(row) + "}")
        image.put(" ".join(rows))
        self._profile_icons[key] = image
        return image

    def _style_profile_button(self, collapsed: bool, is_active: bool) -> None:
        button = self.profile_button
        panel_bg = self.app.c("panel_bg")
        text_fg = self.app.c("text_fg")
        accent = self.app.c("accent")
        try:
            if collapsed:
                color = accent if is_active else text_fg
                button.configure(
                    relief=tk.FLAT, bd=0, highlightthickness=0, padx=2, pady=6,
                    font=COLLAPSED_ICON_FONT, bg=panel_bg, fg=color,
                    activebackground=panel_bg, activeforeground=color,
                )
                try:
                    button.configure(image=self._person_icon(color, panel_bg), text="")
                    button.normal_text = ""
                except tk.TclError:
                    # No icon support on this Tk build: fall back to the letter P.
                    button.configure(image="", text=PROFILE_FALLBACK_ICON)
                    button.normal_text = PROFILE_FALLBACK_ICON
            else:
                button.configure(image="", text=PROFILE_TITLE)
                button.normal_text = PROFILE_TITLE
                if is_active:
                    button.configure(
                        relief=tk.RAISED, bd=1, padx=10, pady=5, font=EXPANDED_NAV_FONT,
                        bg=accent, fg="#ffffff", activebackground=accent, activeforeground="#ffffff",
                    )
                else:
                    button.configure(
                        relief=tk.RAISED, bd=1, padx=10, pady=5, font=EXPANDED_NAV_FONT,
                        bg=self.app.c("button_bg"), fg=text_fg,
                        activebackground=self.app.c("button_active"), activeforeground=text_fg,
                    )
        except tk.TclError:
            pass
