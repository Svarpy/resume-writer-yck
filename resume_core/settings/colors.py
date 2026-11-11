"""Forgiving colour parsing for the Settings page.

Accepts ``#1a2b3c``, ``1a2b3c``, ``#abc``, ``rgb(26, 43, 60)``, ``26 43 60``,
``26,43,60``, ``hsl(210, 40%, 17%)`` and common colour names, and always
returns ``#rrggbb`` (lower case).
"""

from __future__ import annotations

import colorsys
import re

_NAMED = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
    "yellow": "#ffff00", "orange": "#ffa500", "purple": "#800080", "pink": "#ffc0cb", "brown": "#a52a2a",
    "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0", "gold": "#ffd700", "navy": "#000080",
    "teal": "#008080", "cyan": "#00ffff", "magenta": "#ff00ff", "lime": "#00ff00", "maroon": "#800000",
    "olive": "#808000", "indigo": "#4b0082", "violet": "#ee82ee", "crimson": "#dc143c", "coral": "#ff7f50",
    "salmon": "#fa8072", "turquoise": "#40e0d0", "skyblue": "#87ceeb", "royalblue": "#4169e1",
    "dodgerblue": "#1e90ff", "tomato": "#ff6347", "orchid": "#da70d6", "slategray": "#708090",
}

_NUMBER = r"\s*(-?\d+(?:\.\d+)?)\s*(%?)\s*"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _channel(number: str, percent: str) -> int:
    value = float(number)
    if percent:
        value = value * 255 / 100
    if not 0 <= value <= (255.0001):
        raise ValueError("colour channels must be between 0 and 255")
    return int(round(value))


def parse_color(text: str) -> str:
    """Return ``text`` as ``#rrggbb`` or raise ``ValueError`` with a friendly message."""
    raw = (text or "").strip().lower()
    if not raw:
        raise ValueError("enter a colour")
    if raw in _NAMED:
        return _NAMED[raw]

    hex_text = raw[1:] if raw.startswith("#") else raw
    if re.fullmatch(r"[0-9a-f]{6}", hex_text):
        return "#" + hex_text
    if re.fullmatch(r"[0-9a-f]{3}", hex_text):
        return "#" + "".join(ch * 2 for ch in hex_text)

    match = re.fullmatch(r"(rgba?|hsla?)\s*\((.*)\)", raw)
    func, body = (match.group(1), match.group(2)) if match else ("rgb", raw)
    parts = [p for p in re.split(r"[\s,/]+", body.strip()) if p]
    if func.startswith("hsl"):
        if len(parts) not in (3, 4):
            raise ValueError("use hsl(hue, saturation%, lightness%)")
        try:
            hue = float(parts[0].rstrip("deg")) % 360 / 360
            sat = _clamp(float(parts[1].rstrip("%")), 0, 100) / 100
            light = _clamp(float(parts[2].rstrip("%")), 0, 100) / 100
        except ValueError:
            raise ValueError("use hsl(hue, saturation%, lightness%)") from None
        red, green, blue = colorsys.hls_to_rgb(hue, light, sat)
        return "#%02x%02x%02x" % (round(red * 255), round(green * 255), round(blue * 255))

    if len(parts) not in (3, 4):
        raise ValueError("use #rrggbb, rgb(255, 255, 255), hsl(...) or a colour name")
    channels = []
    for part in parts[:3]:
        number = re.fullmatch(_NUMBER, part)
        if not number:
            raise ValueError("use #rrggbb, rgb(255, 255, 255), hsl(...) or a colour name")
        channels.append(_channel(number.group(1), number.group(2)))
    return "#%02x%02x%02x" % tuple(channels)
