"""One scroll handler for the whole app: the wheel and the trackpad scroll the visible page wherever
the pointer is, not only over its scroll bar.

Each page that can scroll offers ``scroll_target()`` returning the canvas or text widget to move (or None).
A text box that has more lines than it shows keeps scrolling itself while the pointer is over it.
"""

from __future__ import annotations

import sys
import tkinter as tk
from typing import Callable, Optional


class ScrollRouter:
    def __init__(self, root: tk.Misc, current_page: Callable[[], Optional[object]]) -> None:
        self.root = root
        self.current_page = current_page
        for sequence, handler in (
            ("<MouseWheel>", self._on_wheel),                # mouse wheel (Windows, macOS)
            ("<TouchpadScroll>", self._on_touchpad),         # two-finger trackpad scroll (Tk 9 on macOS)
            ("<Button-4>", lambda event: self._scroll_units(event, -1)),   # X11
            ("<Button-5>", lambda event: self._scroll_units(event, 1)),
        ):
            try:
                root.bind_all(sequence, handler, add="+")
            except tk.TclError:
                continue  # this Tk has no such event

    # -- which widget moves ------------------------------------------------------------------
    def _target(self, event) -> Optional[tk.Misc]:
        page = self.current_page()
        getter = getattr(page, "scroll_target", None)
        target = getter() if callable(getter) else None
        if target is None or not target.winfo_ismapped():
            return None
        under = getattr(event, "widget", None)
        if isinstance(under, tk.Text) and under is not target and under.yview() != (0.0, 1.0):
            return None            # a text box with its own overflow handles the wheel itself
        return target

    # -- handlers ----------------------------------------------------------------------------
    def _scroll_units(self, event, amount: int) -> None:
        target = self._target(event)
        if target is not None and amount:
            target.yview_scroll(amount, "units")

    def _on_wheel(self, event) -> None:
        delta = event.delta
        if sys.platform != "darwin":
            delta = int(delta / 120)
        if delta:
            self._scroll_units(event, -delta)

    def _on_touchpad(self, event) -> None:
        target = self._target(event)
        if target is None:
            return
        try:
            _dx, dy = self.root.tk.call("tk::PreciseScrollDeltas", event.delta)
        except tk.TclError:
            return
        if not dy:
            return
        if isinstance(target, tk.Canvas):
            box = target.bbox("all")
            if box and box[3] > box[1]:
                # Canvases only scroll by units/pages, so move by a fraction of the content height.
                target.yview_moveto(target.yview()[0] - float(dy) / (box[3] - box[1]))
        else:
            target.yview_scroll(-1 if float(dy) > 0 else 1, "units")
