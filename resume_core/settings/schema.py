"""Declarative registry of every user-controllable application setting.

Each :class:`SettingDef` describes one setting: where it lives in
``settings.json`` (dotted ``key``), how the Settings page groups and renders it
(``category``, ``label``, ``kind``), its default, and validation limits. The
Settings page, the JSON store and the validators are all driven from this one
registry, so adding a setting means adding one entry here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SETTINGS_FORMAT_VERSION = 1

# Section kinds the Writer page and the DOCX renderer understand.
SECTION_KINDS: tuple[str, ...] = (
    "paragraph",   # free text, justified paragraphs
    "skills",      # "Label: values" lines, bold label
    "experience",  # company / role / dated lines + bullets
    "bullets",     # bullets, dated lines or plain lines (certifications, projects, ...)
    "education",   # filled from Settings > Education (no Writer text box)
    "keywords",    # Writer text box that feeds DOCX keyword metadata (not rendered)
)
SECTION_WIDTHS: tuple[str, ...] = ("half", "full")
KINDS_WITHOUT_WRITER_BOX: tuple[str, ...] = ("education",)
KINDS_NOT_RENDERED: tuple[str, ...] = ("keywords",)

SECTION_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
FILENAME_PLACEHOLDERS: tuple[str, ...] = ("company", "date", "name", "username")

DEFAULT_OUTPUT_DIRECTORY = str(Path.home() / "Documents" / "Resumes")

FILE_NAME_FIELD = "file_name"  # pseudo-field key usable in validation.required_fields


@dataclass(frozen=True)
class FieldDef:
    """One column of a ``records`` setting (a list of structured rows)."""

    key: str
    label: str
    kind: str = "str"  # str | bool | int | choice | text | lines
    default: Any = ""
    choices: tuple[str, ...] = ()
    min: Optional[int] = None
    max: Optional[int] = None
    width: int = 18
    advanced: bool = False


@dataclass(frozen=True)
class SettingDef:
    key: str
    category: str
    label: str
    kind: str  # bool | str | int | choice | path | color | str_list | int_list | records | checklist | info | action
    default: Any = None
    description: str = ""
    choices: tuple[str, ...] = ()
    min: Optional[int] = None
    max: Optional[int] = None
    fields: tuple[FieldDef, ...] = ()
    # Name of a validator in ``store`` run after type validation (cross-field rules).
    check: str = ""
    # info/action rows are shown on the Settings page but never written to JSON.
    stored: bool = True
    # Hidden on the Settings page until "Show Advanced" is switched on (still searchable).
    advanced: bool = False
    # "user": one value per user. "format": one value per saved resume format.
    scope: str = "user"
    extra: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


_SECTION_FIELDS = (
    FieldDef("key", "Key", "str", "", width=14, advanced=True),
    FieldDef("label", "Writer label", "str", "", width=22),
    FieldDef("heading", "DOCX heading", "str", "", width=20),
    FieldDef("kind", "Kind", "choice", "paragraph", choices=SECTION_KINDS, width=12),
    FieldDef("width", "Width", "choice", "half", choices=SECTION_WIDTHS, width=6, advanced=True),
    FieldDef("show_heading", "Show heading", "bool", True, advanced=True),
    FieldDef("enabled", "Show", "bool", True),
    FieldDef("min_words", "Min words", "int", 0, min=0, max=100000, width=6),
    FieldDef("max_words", "Max words", "int", 0, min=0, max=100000, width=6),
)

_EDUCATION_FIELDS = (
    FieldDef("label", "Label", "str", "", width=22),
    FieldDef("enabled", "Include in resume", "bool", True),
    FieldDef(
        "text",
        "Entry (one line per row; separate the date with a Tab or put it after a '|')",
        "text",
        "",
    ),
)

_COMPANY_FIELDS = (
    FieldDef("name", "Name", "str", "", width=20),
    FieldDef("aliases", "Match lines starting with (one per line)", "lines", []),
    FieldDef("default_date", "Company date if missing", "str", "", width=24),
    FieldDef("role_dates", "Role dates if missing, newest role first (one per line)", "lines", []),
)


def _section(
    key: str,
    label: str,
    kind: str,
    *,
    heading: str = "",
    width: str = "half",
    enabled: bool = True,
    min_words: int = 0,
    max_words: int = 0,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "heading": heading,
        "kind": kind,
        "width": width,
        "enabled": enabled,
        "show_heading": True,
        "min_words": min_words,
        "max_words": max_words,
    }


DEFAULT_SECTIONS: list[dict[str, Any]] = [
    _section("summary", "Summary", "paragraph", min_words=41, max_words=50),
    _section("skills", "Skills", "skills"),
    _section("experience", "Job Experience", "experience", width="full"),
    _section("education", "Education", "education"),
    _section("certifications", "Certifications", "bullets"),
    _section("top_skills", "Top 5 Skills For Metadata", "keywords"),
]

DEFAULT_REQUIRED_FIELDS: list[str] = ["summary", "skills", "experience", "top_skills", FILE_NAME_FIELD]

SETTING_DEFS: tuple[SettingDef, ...] = (
    # --- Appearance -------------------------------------------------------
    SettingDef(
        "appearance.dark_mode", "Appearance", "Dark Mode", "bool", True,
        "Use the dark colour theme.",
    ),
    SettingDef(
        "appearance.accent_color", "Appearance", "Accent Colour", "color", "#0a84ff",
        "Colour of buttons and the active page. Type #1a2b3c, rgb(26, 43, 60), hsl(...) or a name like orange.",
    ),
    SettingDef(
        "appearance.editor_font_size", "Appearance", "Writer Text Size", "int", 12,
        "Font size of the Writer page text boxes (screen only; does not change the resume).",
        min=8, max=28,
    ),
    SettingDef(
        "appearance.sidebar_mode", "Appearance", "Sidebar On Startup", "choice", "auto",
        "auto collapses the sidebar when the window is narrower than the width below.",
        choices=("auto", "expanded", "collapsed"),
        advanced=True,
    ),
    SettingDef(
        "appearance.sidebar_auto_collapse_width", "Appearance", "Sidebar Auto-Collapse Width", "int", 1000,
        "Window width in pixels below which the sidebar starts collapsed (auto mode).",
        min=400, max=4000,
        advanced=True,
    ),
    # --- Duplicate Check --------------------------------------------------
    SettingDef(
        "duplicate_check.enabled", "Duplicate Check", "Enable Duplicate Check", "bool", True,
        "Block Generate when a matching file already exists in the folders below.",
    ),
    SettingDef(
        "duplicate_check.directories", "Duplicate Check", "Folders To Check", "str_list",
        ["{output_dir}", "{output_dir}/#applied"],
        "One folder per line. {output_dir} expands to the Output Directory setting.",
    ),
    SettingDef(
        "duplicate_check.extensions", "Duplicate Check", "File Types To Check", "str_list",
        [".docx", ".pdf"],
        "Only files with these extensions count as duplicates (one per line, e.g. .docx).",
        advanced=True,
    ),
    SettingDef(
        "duplicate_check.case_sensitive", "Duplicate Check", "Case Sensitive Match", "bool", False,
        "When off, 'Acme' also matches 'acme'. The File Name value may appear anywhere in an existing file name.",
        advanced=True,
    ),
    # --- Education --------------------------------------------------------
    SettingDef(
        "education.entries", "Education", "Education Entries", "records", [],
        "Each included entry is written to the Education section. Add, remove, reorder or switch entries off here.",
        fields=_EDUCATION_FIELDS,
    ),
    # --- Experience Parsing ----------------------------------------------
    SettingDef(
        "experience.known_companies", "Experience Parsing", "Known Companies", "records", [],
        "Optional. When a pasted company or role line has no date, the dates configured here are filled in.",
        fields=_COMPANY_FIELDS,
        advanced=True,
    ),
    # --- Fonts ------------------------------------------------------------
    SettingDef(
        "fonts.font_choices", "Fonts", "Font Choices", "str_list",
        ["Aptos", "Arial", "Calibri", "Cambria", "Garamond", "Georgia", "Times New Roman", "Verdana"],
        "Fonts offered on the Writer page (one per line). Add any font installed on the machine that opens the DOCX.",
        scope="format",
    ),
    SettingDef(
        "fonts.name_size_choices", "Fonts", "Name Size Choices", "int_list", [14, 15, 16, 17, 18, 20],
        "Point sizes offered for the name (one per line).", min=6, max=72,
        scope="format",
    ),
    SettingDef(
        "fonts.heading_size_choices", "Fonts", "Heading Size Choices", "int_list", [11, 12, 13, 14],
        "Point sizes offered for section headings (one per line).", min=6, max=72,
        scope="format",
    ),
    SettingDef(
        "fonts.body_size_choices", "Fonts", "Text Size Choices", "int_list", [10, 11, 12],
        "Point sizes offered for body text (one per line).", min=6, max=72,
        scope="format",
    ),
    # --- Metadata ---------------------------------------------------------
    SettingDef(
        "metadata.author", "Metadata", "Author", "str", "",
        "DOCX author property. Leave blank to use your Personal Details name.",
    ),
    SettingDef(
        "metadata.keyword_count", "Metadata", "Keyword Count", "int", 5,
        "How many entries of the keywords section are written to the DOCX keywords property.",
        min=0, max=50,
        advanced=True,
    ),
    SettingDef(
        "metadata.subject", "Metadata", "Subject", "str", "my resume",
        "DOCX subject property.",
    ),
    SettingDef(
        "metadata.title_template", "Metadata", "Title Template", "str", "{name} Resume",
        "DOCX title property. {name} is replaced with the resume name.",
        advanced=True,
    ),
    # --- Output -----------------------------------------------------------
    SettingDef(
        "output.company_placeholder", "Output", "File Name Placeholder", "str", "XXX",
        "Shown in the file name while the Writer File Name field is empty.",
        advanced=True,
    ),
    SettingDef(
        "output.date_format", "Output", "File Name Date Format", "str", "%d%b",
        "Python strftime format for {date}, e.g. %d%b gives 09Nov.",
        advanced=True,
    ),
    SettingDef(
        "output.directory", "Output", "Output Directory", "path", DEFAULT_OUTPUT_DIRECTORY,
        "Folder generated resumes are saved to.",
    ),
    SettingDef(
        "output.filename_template", "Output", "File Name Template", "str", "Resume{company}{date}",
        "Placeholders: {company} (Writer File Name field, required), {date}, {name}, {username}. '.docx' is appended.",
        check="filename_template",
    ),
    SettingDef(
        "output.preview", "Output", "Resulting Path", "info", None,
        "Where the next resume will be written, using the values above.",
        stored=False,
    ),
    # --- Personal Details -------------------------------------------------
    SettingDef("personal.email", "Personal Details", "Email", "str", "", "Shown in the resume header (mailto link)."),
    SettingDef("personal.location", "Personal Details", "Location", "str", "", "Shown in the resume header."),
    SettingDef("personal.name", "Personal Details", "Name", "str", "", "Shown at the top of the resume."),
    SettingDef(
        "personal.tagline", "Personal Details", "Tagline", "str", "",
        "Optional line under the name, for formats that have one (e.g. 'Software Engineer'). Leave blank to omit it.",
    ),
    SettingDef("personal.phone", "Personal Details", "Phone", "str", "", "Shown in the resume header (tel link)."),
    # --- Resume Sections --------------------------------------------------
    SettingDef(
        "sections.items", "Resume Sections", "Sections", "records", DEFAULT_SECTIONS,
        "Order here is the order in the resume. Add sections, rename them, change how they render, or hide them. "
        "Leave 'DOCX heading' blank to use the selected format's heading (or the label in capitals).",
        fields=_SECTION_FIELDS,
        check="sections",
        scope="format",
    ),
    # --- Updates ----------------------------------------------------------
    SettingDef(
        "updates.auto_check", "Updates", "Check For Updates On Launch", "bool", True,
        "Check GitHub Releases for a newer version about once a week after sign-in.",
    ),
    SettingDef(
        "updates.check_now", "Updates", "Check Now", "action", None,
        "Check GitHub Releases immediately, ignoring the weekly timer.",
        stored=False,
    ),
    # --- Validation -------------------------------------------------------
    SettingDef(
        "validation.required_fields", "Validation", "Required Fields", "checklist",
        list(DEFAULT_REQUIRED_FIELDS),
        "Tick the fields that must be filled before Generate is enabled. Word limits are set per section.",
        scope="format",
    ),
    # --- Writer -----------------------------------------------------------
    SettingDef(
        "writer.clear_after_generate", "Writer", "Clear Fields After Generate", "bool", True,
        "Empty the Writer text boxes and the File Name field after a resume is saved.",
    ),
)

SETTING_DEFS_BY_KEY: dict[str, SettingDef] = {d.key: d for d in SETTING_DEFS}
STORED_DEFS: tuple[SettingDef, ...] = tuple(d for d in SETTING_DEFS if d.stored)


FORMAT_SCOPED_KEYS: frozenset[str] = frozenset(d.key for d in STORED_DEFS if d.scope == "format")


def categories() -> list[str]:
    """Category names in alphabetical order."""
    return sorted({d.category for d in SETTING_DEFS}, key=str.casefold)


def settings_in_category(category: str) -> list[SettingDef]:
    """Settings of one category in alphabetical order by label."""
    return sorted((d for d in SETTING_DEFS if d.category == category), key=lambda d: d.label.casefold())
