"""Version contract and GitHub Release asset naming helpers.

``APP_VERSION`` in ``resume_writer.constants`` is the single source of truth.
Git tags and Release assets must use the same ``vX.Y.Z`` string.

Shared by the release pipeline and the in-app updater.
"""

from __future__ import annotations

import re
import sys
from typing import Optional, Tuple

from resume_writer.constants import APP_VERSION

__all__ = [
    "APP_VERSION",
    "VERSION_RE",
    "normalize_version",
    "parse_version",
    "compare_versions",
    "is_newer",
    "version_is_newer",
    "display_name",
    "display_app_name",
    "pyinstaller_name",
    "compact_version_slug",
    "macos_asset_name",
    "windows_asset_name",
    "asset_names_for",
    "asset_name_for_platform",
]

# Canonical release tags: leading v + three numeric components (e.g. v3.0.0).
VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

# Looser parse for compare (optional leading v; optional pre-release label).
_LOOSE_VERSION_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:[-+](?P<label>.+))?$",
    re.IGNORECASE,
)


def normalize_version(version: str) -> str:
    """Return a canonical ``vX.Y.Z`` string (release / tag form).

    Accepts ``v3.0.0`` or ``3.0.0``. Rejects labels and partial versions.
    """
    text = (version or "").strip()
    if not text:
        raise ValueError("Version string is empty")
    if not text.startswith("v"):
        text = f"v{text}"
    if not VERSION_RE.match(text):
        raise ValueError(f"Invalid version {version!r}; expected vX.Y.Z")
    return text


def parse_version(version: str) -> Tuple[int, int, int]:
    """Parse ``vX.Y.Z`` (or ``X.Y.Z``) into ``(major, minor, patch)``."""
    normalized = normalize_version(version)
    match = VERSION_RE.match(normalized)
    assert match is not None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _parse_loose(version: str) -> Tuple[int, int, int, str]:
    text = (version or "").strip()
    if not text:
        raise ValueError("Version string is empty")
    match = _LOOSE_VERSION_RE.match(text)
    if not match:
        # Fall back to strict normalize then re-parse.
        normalized = normalize_version(text)
        match = _LOOSE_VERSION_RE.match(normalized)
        if not match:
            raise ValueError(f"Unrecognized version string: {version!r}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        (match.group("label") or "").lower(),
    )


def compare_versions(left: str, right: str) -> int:
    """Compare two versions.

    Returns ``-1`` if left < right, ``0`` if equal, ``1`` if left > right.
    Labeled / pre-release builds sort before the same numeric release.
    """
    l_maj, l_min, l_pat, l_label = _parse_loose(left)
    r_maj, r_min, r_pat, r_label = _parse_loose(right)
    for l_part, r_part in ((l_maj, r_maj), (l_min, r_min), (l_pat, r_pat)):
        if l_part < r_part:
            return -1
        if l_part > r_part:
            return 1
    if l_label == r_label:
        return 0
    if not l_label:
        return 1
    if not r_label:
        return -1
    if l_label < r_label:
        return -1
    if l_label > r_label:
        return 1
    return 0


def is_newer(candidate: str, current: Optional[str] = None) -> bool:
    """True when ``candidate`` is strictly newer than ``current`` (default: APP_VERSION)."""
    baseline = APP_VERSION if current is None else current
    return compare_versions(candidate, baseline) > 0


def version_is_newer(candidate: str, current: str) -> bool:
    """Alias for updater code that always passes both sides explicitly."""
    return compare_versions(candidate, current) > 0


def display_name(version: Optional[str] = None) -> str:
    """Human-facing app name, e.g. ``Resume Writer v3.0.0``."""
    ver = normalize_version(APP_VERSION if version is None else version)
    return f"Resume Writer {ver}"


def display_app_name(version: Optional[str] = None) -> str:
    """Alias of :func:`display_name`."""
    return display_name(version)


def pyinstaller_name(version: Optional[str] = None) -> str:
    """PyInstaller ``--name`` value (same as :func:`display_name`)."""
    return display_name(version)


def compact_version_slug(version: Optional[str] = None) -> str:
    """Compact slug used in zip filenames, e.g. ``ResumeWriterv3.0.0``."""
    ver = normalize_version(APP_VERSION if version is None else version)
    return f"ResumeWriter{ver}"


def macos_asset_name(version: Optional[str] = None) -> str:
    """GitHub Release asset for macOS: ``ResumeWritervX.Y.Z.app.zip``."""
    return f"{compact_version_slug(version)}.app.zip"


def windows_asset_name(version: Optional[str] = None) -> str:
    """GitHub Release asset for Windows: ``ResumeWritervX.Y.Z.exe.zip``."""
    return f"{compact_version_slug(version)}.exe.zip"


def asset_names_for(version: Optional[str] = None) -> dict[str, str]:
    """Return macOS and Windows Release asset filenames for ``version``."""
    return {
        "macos": macos_asset_name(version),
        "windows": windows_asset_name(version),
    }


def asset_name_for_platform(
    version: Optional[str] = None,
    platform: Optional[str] = None,
) -> str:
    """Return the Release asset filename for the given platform.

    ``platform`` accepts ``sys.platform`` values (``darwin``, ``win32``, …)
    or short names ``macos`` / ``windows``.
    """
    plat = (platform or sys.platform).lower()
    ver = APP_VERSION if version is None else version
    if plat in ("darwin", "macos", "mac"):
        return macos_asset_name(ver)
    if plat.startswith("win") or plat == "windows":
        return windows_asset_name(ver)
    raise ValueError(f"Unsupported platform for release assets: {plat!r}")
