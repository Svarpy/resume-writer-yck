"""The ``Settings`` model: defaults, validation and change notification (no storage).

Settings are a flat ``dotted.key -> value`` mapping described by
:mod:`resume_core.settings.schema`. User-wide keys and format-scoped keys are kept
apart by the server; this class only validates and tracks them.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date
from typing import Any, Callable, Optional

from resume_core.settings.colors import parse_color
from resume_core.settings.schema import (
    FILE_NAME_FIELD,
    FILENAME_PLACEHOLDERS,
    FORMAT_SCOPED_KEYS,
    KINDS_NOT_RENDERED,
    KINDS_WITHOUT_WRITER_BOX,
    SECTION_KEY_RE,
    SECTION_KINDS,
    SECTION_WIDTHS,
    SETTING_DEFS_BY_KEY,
    SETTINGS_FORMAT_VERSION,
    STORED_DEFS,
    FieldDef,
    SettingDef,
)


class SettingsError(ValueError):
    """Raised when a setting value (or a whole settings document) is invalid."""


# --------------------------------------------------------------------------
# Value validation
# --------------------------------------------------------------------------


def _int_in_range(value: Any, lo: Optional[int], hi: Optional[int], what: str) -> int:
    if isinstance(value, bool):
        raise SettingsError(f"{what} must be a whole number")
    if isinstance(value, str):
        text = value.strip()
        if not re.fullmatch(r"-?\d+", text):
            raise SettingsError(f"{what} must be a whole number")
        value = int(text)
    if not isinstance(value, int):
        raise SettingsError(f"{what} must be a whole number")
    if lo is not None and value < lo:
        raise SettingsError(f"{what} must be at least {lo}")
    if hi is not None and value > hi:
        raise SettingsError(f"{what} must be at most {hi}")
    return value


def _clean_str(value: Any, what: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SettingsError(f"{what} must be text")
    return value.strip()


def _str_list(value: Any, what: str) -> list[str]:
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, (list, tuple)):
        raise SettingsError(f"{what} must be a list of text values")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise SettingsError(f"{what} must only contain text values")
        item = item.strip()
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            out.append(item)
    return out


def _validate_field(field_def: FieldDef, value: Any, row_label: str) -> Any:
    what = f"{row_label} '{field_def.label}'"
    kind = field_def.kind
    if kind == "bool":
        if not isinstance(value, bool):
            raise SettingsError(f"{what} must be true or false")
        return value
    if kind == "int":
        return _int_in_range(value, field_def.min, field_def.max, what)
    if kind == "choice":
        if value not in field_def.choices:
            raise SettingsError(f"{what} must be one of: {', '.join(field_def.choices)}")
        return value
    if kind == "lines":
        return _str_list(value, what)
    if kind == "text":
        if value is None:
            return ""
        if not isinstance(value, str):
            raise SettingsError(f"{what} must be text")
        return value.strip("\n").rstrip()
    return _clean_str(value, what)


def _validate_records(definition: SettingDef, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        raise SettingsError(f"{definition.label} must be a list")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            raise SettingsError(f"{definition.label}: row {index} must be an object")
        row: dict[str, Any] = {}
        for field_def in definition.fields:
            row[field_def.key] = _validate_field(
                field_def,
                raw.get(field_def.key, copy.deepcopy(field_def.default)),
                f"{definition.label} row {index}",
            )
        rows.append(row)
    return rows


def validate_value(definition: SettingDef, value: Any) -> Any:
    """Return the normalised ``value`` for ``definition`` or raise SettingsError."""
    kind = definition.kind
    what = definition.label
    if kind == "bool":
        if not isinstance(value, bool):
            raise SettingsError(f"{what} must be true or false")
        normalized: Any = value
    elif kind == "int":
        normalized = _int_in_range(value, definition.min, definition.max, what)
    elif kind in ("str", "path"):
        normalized = _clean_str(value, what)
        if kind == "path" and not normalized:
            raise SettingsError(f"{what} cannot be empty")
    elif kind == "color":
        try:
            normalized = parse_color(_clean_str(value, what))
        except ValueError as exc:
            raise SettingsError(f"{what}: {exc}") from None
    elif kind == "choice":
        if value not in definition.choices:
            raise SettingsError(f"{what} must be one of: {', '.join(definition.choices)}")
        normalized = value
    elif kind in ("str_list", "checklist"):
        normalized = _str_list(value, what)
    elif kind == "int_list":
        if isinstance(value, str):
            value = value.splitlines()
        if not isinstance(value, (list, tuple)):
            raise SettingsError(f"{what} must be a list of whole numbers")
        numbers: list[int] = []
        for item in value:
            if isinstance(item, str) and not item.strip():
                continue
            number = _int_in_range(item, definition.min, definition.max, what)
            if number not in numbers:
                numbers.append(number)
        normalized = numbers
    elif kind == "records":
        normalized = _validate_records(definition, value)
    else:  # info / action rows carry no value
        raise SettingsError(f"{what} cannot be changed")

    check = _CHECKS.get(definition.check)
    if check is not None:
        normalized = check(definition, normalized)
    _require_non_empty_choices(definition, normalized)
    return normalized


def _require_non_empty_choices(definition: SettingDef, value: Any) -> None:
    if definition.key.startswith("fonts.") and isinstance(value, list) and not value:
        raise SettingsError(f"{definition.label} needs at least one entry")


def _check_filename_template(definition: SettingDef, value: str) -> str:
    if not value:
        raise SettingsError(f"{definition.label} cannot be empty")
    names = re.findall(r"\{([^{}]*)\}", value)
    unknown = [name for name in names if name not in FILENAME_PLACEHOLDERS]
    if unknown:
        allowed = ", ".join("{%s}" % name for name in FILENAME_PLACEHOLDERS)
        raise SettingsError(f"Unknown placeholder {{{unknown[0]}}} in {definition.label}. Allowed: {allowed}")
    if "company" not in names:
        raise SettingsError(f"{definition.label} must contain {{company}}")
    stripped = re.sub(r"\{[^{}]*\}", "", value)
    if "{" in stripped or "}" in stripped:
        raise SettingsError(f"{definition.label} has an unmatched brace")
    if re.search(r'[\\/:*?"<>|]', stripped):
        raise SettingsError(f"{definition.label} cannot contain any of \\ / : * ? \" < > |")
    return value


def _check_sections(definition: SettingDef, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        key = row["key"].strip().lower()
        if not SECTION_KEY_RE.fullmatch(key):
            raise SettingsError(
                f"Section {index}: key must start with a letter and use only a-z, 0-9 and _ (max 32 characters)"
            )
        if key in seen:
            raise SettingsError(f"Section {index}: key '{key}' is used twice")
        if key == FILE_NAME_FIELD:
            raise SettingsError(f"Section {index}: '{FILE_NAME_FIELD}' is reserved")
        seen.add(key)
        row["key"] = key
        if not row["label"]:
            raise SettingsError(f"Section '{key}' needs a Writer label")
        if row["kind"] not in SECTION_KINDS or row["width"] not in SECTION_WIDTHS:
            raise SettingsError(f"Section '{key}' has an invalid kind or width")
        if row["max_words"] and row["min_words"] > row["max_words"]:
            raise SettingsError(f"Section '{key}': min words cannot exceed max words")
    for kind in ("education", "keywords"):
        if sum(1 for row in rows if row["kind"] == kind) > 1:
            raise SettingsError(f"Only one section can use the '{kind}' kind")
    return rows


_CHECKS: dict[str, Callable[[SettingDef, Any], Any]] = {
    "filename_template": _check_filename_template,
    "sections": _check_sections,
}


def validate_date_format(fmt: str) -> str:
    """Raise SettingsError unless ``fmt`` is a usable, non-empty strftime format."""
    fmt = (fmt or "").strip()
    if not fmt:
        raise SettingsError("File Name Date Format cannot be empty")
    try:
        rendered = date.today().strftime(fmt)
    except (ValueError, TypeError) as exc:
        raise SettingsError(f"File Name Date Format is not valid: {exc}") from exc
    if not rendered.strip():
        raise SettingsError("File Name Date Format produced an empty date")
    return fmt


# --------------------------------------------------------------------------
# The Settings object
# --------------------------------------------------------------------------


def _nested_get(raw: dict[str, Any], dotted: str) -> tuple[bool, Any]:
    node: Any = raw
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


def _nested_set(raw: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = raw
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _unknown_paths(raw: Any, prefix: str = "") -> list[str]:
    """Dotted paths in ``raw`` that do not correspond to any known setting."""
    unknown: list[str] = []
    if not isinstance(raw, dict):
        return unknown
    for key, value in raw.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if prefix == "" and key == "version":
            continue
        if path in SETTING_DEFS_BY_KEY:
            continue
        if isinstance(value, dict) and any(k.startswith(path + ".") for k in SETTING_DEFS_BY_KEY):
            unknown.extend(_unknown_paths(value, path))
        else:
            unknown.append(path)
    return unknown


class Settings:
    """In-memory settings for one user (flat ``dotted.key`` → value)."""

    def __init__(
        self,
        values: Optional[dict[str, Any]] = None,
        *,
        defaults: Optional[dict[str, Any]] = None,
    ) -> None:
        # ``defaults`` lets a saved format supply its own starting values (its sections, fonts, ...).
        self._defaults: dict[str, Any] = {d.key: copy.deepcopy(d.default) for d in STORED_DEFS}
        for key, value in (defaults or {}).items():
            self._defaults[key] = copy.deepcopy(value)
        self._values: dict[str, Any] = copy.deepcopy(self._defaults)
        for key, value in (values or {}).items():
            self._values[key] = value
        self._listeners: list[Callable[[tuple[str, ...]], None]] = []

    # -- reading --------------------------------------------------------
    def get(self, key: str) -> Any:
        if key not in self._values:
            raise KeyError(key)
        return copy.deepcopy(self._values[key])

    def default_for(self, key: str) -> Any:
        return copy.deepcopy(self._defaults[key])

    def is_default(self, key: str) -> bool:
        return self._values[key] == self._defaults[key]

    def modified_keys(self) -> list[str]:
        return [d.key for d in STORED_DEFS if not self.is_default(d.key)]

    def all(self) -> dict[str, Any]:
        return copy.deepcopy(self._values)

    # -- writing --------------------------------------------------------
    def set(self, key: str, value: Any) -> Any:
        definition = SETTING_DEFS_BY_KEY.get(key)
        if definition is None or not definition.stored:
            raise SettingsError(f"Unknown setting '{key}'")
        normalized = validate_value(definition, value)
        self._cross_validate(key, normalized)
        self._values[key] = normalized
        self._notify((key,))
        return copy.deepcopy(normalized)

    def reset(self, key: str) -> None:
        self._values[key] = copy.deepcopy(self._defaults[key])
        self._notify((key,))

    def reset_all(self) -> None:
        changed = tuple(k for k in self._values if self._values[k] != self._defaults[k])
        self._values = copy.deepcopy(self._defaults)
        if changed:
            self._notify(changed)

    def load_format_values(self, values: dict[str, Any], defaults: dict[str, Any]) -> None:
        """Swap in another format's settings (its values and its starting values), keeping user-wide ones."""
        for key in FORMAT_SCOPED_KEYS:
            self._defaults[key] = copy.deepcopy(defaults.get(key, SETTING_DEFS_BY_KEY[key].default))
            self._values[key] = copy.deepcopy(values.get(key, self._defaults[key]))
        self._notify(tuple(sorted(FORMAT_SCOPED_KEYS)))

    def all_defaults(self) -> dict[str, Any]:
        return copy.deepcopy(self._defaults)

    def replace_all(self, other: "Settings") -> None:
        changed = tuple(k for k in self._values if self._values[k] != other._values[k])
        self._values = copy.deepcopy(other._values)
        self._defaults = copy.deepcopy(other._defaults)
        if changed:
            self._notify(changed)

    def _cross_validate(self, key: str, value: Any) -> None:
        if key == "output.date_format":
            validate_date_format(value)

    # -- listeners ------------------------------------------------------
    def add_listener(self, callback: Callable[[tuple[str, ...]], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, keys: tuple[str, ...]) -> None:
        for callback in list(self._listeners):
            callback(keys)

    # -- JSON -----------------------------------------------------------
    def to_dict(self, scope: Optional[str] = None) -> dict[str, Any]:
        """Nested settings document; ``scope`` ("user" / "format") limits which settings are included."""
        raw: dict[str, Any] = {"version": SETTINGS_FORMAT_VERSION}
        for definition in STORED_DEFS:
            if scope is not None and definition.scope != scope:
                continue
            _nested_set(raw, definition.key, copy.deepcopy(self._values[definition.key]))
        return raw

    def to_json(self, scope: Optional[str] = None) -> str:
        return json.dumps(self.to_dict(scope), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, raw: Any, *, strict: bool = True, defaults: Optional[dict[str, Any]] = None) -> "Settings":
        if not isinstance(raw, dict):
            raise SettingsError("Settings must be a JSON object")
        unknown = _unknown_paths(raw)
        if unknown and strict:
            raise SettingsError(f"Unknown setting '{unknown[0]}'")
        version = raw.get("version", SETTINGS_FORMAT_VERSION)
        if version != SETTINGS_FORMAT_VERSION:
            raise SettingsError(f"Unsupported settings version {version!r}")
        instance = cls(defaults=defaults)
        for definition in STORED_DEFS:
            present, value = _nested_get(raw, definition.key)
            if not present:
                continue
            instance._values[definition.key] = validate_value(definition, value)
        validate_date_format(instance._values["output.date_format"])
        return instance

    @classmethod
    def from_json(cls, text: str, *, strict: bool = True, defaults: Optional[dict[str, Any]] = None) -> "Settings":
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SettingsError(f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})") from exc
        return cls.from_dict(raw, strict=strict, defaults=defaults)

    # -- convenience accessors -----------------------------------------
    def section_defs(self) -> list[dict[str, Any]]:
        return self.get("sections.items")

    def writer_sections(self) -> list[dict[str, Any]]:
        """Enabled sections that get a text box on the Writer page, in order."""
        return [
            row for row in self.section_defs()
            if row["enabled"] and row["kind"] not in KINDS_WITHOUT_WRITER_BOX
        ]

    def rendered_sections(self) -> list[dict[str, Any]]:
        """Enabled sections written to the DOCX, in order."""
        return [
            row for row in self.section_defs()
            if row["enabled"] and row["kind"] not in KINDS_NOT_RENDERED
        ]

    def required_fields(self) -> list[str]:
        return self.get("validation.required_fields")

    def education_entries(self) -> list[str]:
        return [
            row["text"] for row in self.get("education.entries")
            if row["enabled"] and row["text"].strip()
        ]


def known_field_keys(settings: Settings) -> list[tuple[str, str]]:
    """(key, label) pairs that can be marked required: Writer sections + the File Name field."""
    pairs = [(row["key"], row["label"]) for row in settings.writer_sections()]
    pairs.append((FILE_NAME_FIELD, "File Name"))
    return pairs
