"""Application-wide constants and default content values."""

from __future__ import annotations

import re
from pathlib import Path

AUTHOR_NAME = "Yashashchandra Kollu"
EMAIL = "yashashchandrakollu1@gmail.com"
PHONE = "+1 (205) 897 7790"
PHONE_LINK = "tel:+1%20(205)%20897%207790"
LOCATION = "Atlanta, GA"
APP_VERSION = "v3.0.0"
DEFAULT_OUTPUT_DIR = Path("/Users/yck/Desktop/CLGENAPPL")

FONT_CHOICES = (
    "Aptos",
    "Arial",
    "Calibri",
    "Cambria",
    "Garamond",
    "Georgia",
    "Times New Roman",
    "Verdana",
)
NAME_SIZE_CHOICES = ("14", "15", "16", "17", "18", "20")
HEADING_SIZE_CHOICES = ("11", "12", "13", "14")
BODY_SIZE_CHOICES = ("10", "11", "12")
MONTH_PATTERN = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
DATE_RANGE_RE = re.compile(
    rf"\b(?:{MONTH_PATTERN})\s+\d{{4}}\s*(?:-|–|—|to)\s*(?:Present|Current|(?:{MONTH_PATTERN})\s+\d{{4}})\b",
    re.IGNORECASE,
)
COMPANY_DATE_DEFAULTS = {
    "first_horizon": "August 2025 – Present",
    "dbs": "July 2022 – July 2024",
    "value_labs": "February 2021 – March 2022",
}
COMPANY_ALIASES = {
    "first_horizon": ("first horizon bank",),
    "dbs": ("dbs bank", "dbs tech india"),
    "value_labs": ("value labs",),
}
ROLE_DATE_DEFAULTS_BY_COMPANY = {
    "first_horizon": ("August 2025 – Present",),
    "dbs": ("September 2023 – July 2024", "July 2022 – September 2023"),
    "value_labs": ("February 2021 – March 2022",),
}

THEMES = {
    "light": {
        "app_bg": "#f5f5f7",
        "panel_bg": "#ffffff",
        "text_bg": "#ffffff",
        "text_fg": "#1d1d1f",
        "muted_fg": "#6e6e73",
        "accent": "#007aff",
        "border": "#d2d2d7",
        "button_bg": "#f5f5f7",
        "button_active": "#e8e8ed",
        "disabled_bg": "#8e8e93",
        "disabled_fg": "#ffffff",
        "error_fg": "#b91c1c",
        "ok_fg": "#166534",
        "select_bg": "#acd7ff",
        "toggle_track": "#d1d1d6",
        "toggle_knob": "#ffffff",
        "toggle_text": "#1d1d1f",
    },
    "dark": {
        "app_bg": "#000000",
        "panel_bg": "#1c1c1e",
        "text_bg": "#1c1c1e",
        "text_fg": "#f5f5f7",
        "muted_fg": "#a1a1a6",
        "accent": "#0a84ff",
        "border": "#38383a",
        "button_bg": "#2c2c2e",
        "button_active": "#3a3a3c",
        "disabled_bg": "#2c2c2e",
        "disabled_fg": "#636366",
        "error_fg": "#fca5a5",
        "ok_fg": "#86efac",
        "select_bg": "#005ecb",
        "toggle_track": "#30d158",
        "toggle_knob": "#ffffff",
        "toggle_text": "#f5f5f7",
    },
}

DEFAULT_MASTERS_EDUCATION = (
    "Master of Science in Computer Science\tAugust 2024 – May 2026\n"
    "University of Alabama at Birmingham, AL  |  GPA: 4.0 / 4.0"
)
DEFAULT_BACHELORS_EDUCATION = (
    "Bachelor of Technology in Information Technology\tAugust 2018 – July 2022\n"
    "Institute of Aeronautical Engineering, Hyderabad, India | GPA: 3.5 / 4.0"
)
