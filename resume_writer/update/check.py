"""Query public GitHub Releases for a newer OS-specific build."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

from resume_writer.constants import APP_VERSION
from resume_writer.version import (
    asset_name_for_platform,
    normalize_version,
    version_is_newer,
)

GITHUB_OWNER = "Svarpy"
GITHUB_REPO = "resume-writer-yck"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

DEFAULT_TIMEOUT_SECONDS = 15

UrlOpen = Callable[..., Any]


class UpdateCheckError(Exception):
    """Non-fatal update-check failure (network / API / parse)."""


@dataclass(frozen=True)
class AvailableUpdate:
    version: str
    tag_name: str
    asset_name: str
    download_url: str
    release_name: str = ""
    size: Optional[int] = None

    @property
    def display_version(self) -> str:
        return self.version


def _default_urlopen(request: urllib.request.Request, *, timeout: float):
    context = ssl.create_default_context()
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def fetch_releases(
    *,
    url: str = RELEASES_API_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    urlopen: Optional[UrlOpen] = None,
) -> list[dict[str, Any]]:
    """Return the GitHub Releases JSON list (public API, no auth)."""
    opener = urlopen or _default_urlopen
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ResumeWriter-Updater/{APP_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise UpdateCheckError(f"GitHub Releases HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise UpdateCheckError(f"Network error contacting GitHub Releases: {exc.reason}") from exc
    except TimeoutError as exc:
        raise UpdateCheckError("Timed out contacting GitHub Releases") from exc
    except OSError as exc:
        raise UpdateCheckError(f"Network error contacting GitHub Releases: {exc}") from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError("Invalid JSON from GitHub Releases") from exc
    if not isinstance(payload, list):
        raise UpdateCheckError("Unexpected GitHub Releases payload")
    return [item for item in payload if isinstance(item, dict)]


def _asset_download_url(asset: dict[str, Any]) -> Optional[str]:
    for key in ("browser_download_url", "url"):
        value = asset.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def find_newer_release(
    releases: list[dict[str, Any]],
    *,
    current_version: str = APP_VERSION,
    platform: Optional[str] = None,
) -> Optional[AvailableUpdate]:
    """Pick the newest release newer than ``current_version`` with the OS asset."""
    best: Optional[AvailableUpdate] = None
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = str(release.get("tag_name") or "").strip()
        if not tag:
            continue
        try:
            version = normalize_version(tag)
        except ValueError:
            continue
        if not version_is_newer(version, current_version):
            continue
        try:
            wanted = asset_name_for_platform(version, platform)
        except ValueError:
            return None
        assets = release.get("assets") or []
        if not isinstance(assets, list):
            continue
        match: Optional[dict[str, Any]] = None
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            if name == wanted:
                match = asset
                break
        if match is None:
            continue
        download_url = _asset_download_url(match)
        if not download_url:
            continue
        size_raw = match.get("size")
        size = int(size_raw) if isinstance(size_raw, int) else None
        candidate = AvailableUpdate(
            version=version,
            tag_name=tag,
            asset_name=wanted,
            download_url=download_url,
            release_name=str(release.get("name") or tag),
            size=size,
        )
        if best is None or version_is_newer(candidate.version, best.version):
            best = candidate
    return best


def check_for_available_update(
    *,
    current_version: str = APP_VERSION,
    platform: Optional[str] = None,
    url: str = RELEASES_API_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    urlopen: Optional[UrlOpen] = None,
) -> Optional[AvailableUpdate]:
    """Fetch releases and return a newer OS asset, or ``None``.

    Raises ``UpdateCheckError`` on network/API failures (callers should fail soft).
    """
    releases = fetch_releases(url=url, timeout=timeout, urlopen=urlopen)
    return find_newer_release(
        releases,
        current_version=current_version,
        platform=platform,
    )
