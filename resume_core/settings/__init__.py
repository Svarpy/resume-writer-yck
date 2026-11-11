"""Settings schema, validation and the ``Settings`` model."""

from __future__ import annotations

from resume_core.settings.model import (
    Settings,
    SettingsError,
    known_field_keys,
    validate_date_format,
    validate_value,
)
from resume_core.settings.schema import (
    FILE_NAME_FIELD,
    FORMAT_SCOPED_KEYS,
    SECTION_KINDS,
    SETTING_DEFS,
    SETTING_DEFS_BY_KEY,
    FieldDef,
    SettingDef,
    categories,
    settings_in_category,
)

__all__ = [
    "FILE_NAME_FIELD",
    "FORMAT_SCOPED_KEYS",
    "FieldDef",
    "SECTION_KINDS",
    "SETTING_DEFS",
    "SETTING_DEFS_BY_KEY",
    "SettingDef",
    "Settings",
    "SettingsError",
    "categories",
    "known_field_keys",
    "settings_in_category",
    "validate_date_format",
    "validate_value",
]
