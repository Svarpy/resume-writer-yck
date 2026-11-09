"""Download and lightly verify GitHub Release zip assets."""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

from resume_writer.constants import APP_VERSION
from resume_writer.paths import get_data_root
from resume_writer.update.http_ssl import create_ssl_context

DEFAULT_TIMEOUT_SECONDS = 120
UrlOpen = Callable[..., Any]


class UpdateDownloadError(Exception):
    """Download or zip verification failed."""


def updates_work_dir() -> Path:
    path = get_data_root() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_urlopen(request: urllib.request.Request, *, timeout: float):
    return urllib.request.urlopen(
        request,
        timeout=timeout,
        context=create_ssl_context(),
    )


def download_asset(
    download_url: str,
    dest_path: Path,
    *,
    expected_size: Optional[int] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    urlopen: Optional[UrlOpen] = None,
) -> Path:
    """Download ``download_url`` to ``dest_path`` (atomic replace when possible)."""
    opener = urlopen or _default_urlopen
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".partial")
    if tmp_path.exists():
        try:
            tmp_path.unlink()
        except OSError:
            pass

    request = urllib.request.Request(
        download_url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": f"ResumeWriter-Updater/{APP_VERSION}",
        },
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            with tmp_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    handle.write(chunk)
    except urllib.error.HTTPError as exc:
        _safe_unlink(tmp_path)
        raise UpdateDownloadError(f"Download HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        _safe_unlink(tmp_path)
        raise UpdateDownloadError(f"Download network error: {exc.reason}") from exc
    except TimeoutError as exc:
        _safe_unlink(tmp_path)
        raise UpdateDownloadError("Download timed out") from exc
    except OSError as exc:
        _safe_unlink(tmp_path)
        raise UpdateDownloadError(f"Download failed: {exc}") from exc

    if expected_size is not None and expected_size >= 0:
        actual = tmp_path.stat().st_size
        if actual != expected_size:
            _safe_unlink(tmp_path)
            raise UpdateDownloadError(
                f"Downloaded size mismatch (expected {expected_size}, got {actual})"
            )

    tmp_path.replace(dest_path)
    return dest_path


def verify_release_zip(zip_path: Path, *, platform: Optional[str] = None) -> str:
    """Open the zip and confirm it contains a macOS ``.app`` or Windows ``.exe``.

    Returns a short kind label (``app`` or ``exe``) on success.
    """
    plat = (platform or sys.platform).lower()
    path = Path(zip_path)
    if not path.is_file():
        raise UpdateDownloadError(f"Update file missing: {path}")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if not names:
                raise UpdateDownloadError("Update zip is empty")
            bad = archive.testzip()
            if bad is not None:
                raise UpdateDownloadError(f"Corrupt zip member: {bad}")
            if plat in ("darwin", "macos", "mac"):
                if not any(_looks_like_macos_app_entry(name) for name in names):
                    raise UpdateDownloadError("Update zip does not contain a .app bundle")
                return "app"
            if plat.startswith("win"):
                if not any(name.lower().endswith(".exe") and not name.endswith("/") for name in names):
                    raise UpdateDownloadError("Update zip does not contain an .exe")
                return "exe"
            raise UpdateDownloadError(f"Unsupported platform for verify: {plat!r}")
    except zipfile.BadZipFile as exc:
        raise UpdateDownloadError("Update file is not a valid zip") from exc
    except OSError as exc:
        raise UpdateDownloadError(f"Could not read update zip: {exc}") from exc


def _looks_like_macos_app_entry(name: str) -> bool:
    parts = Path(name).parts
    return any(part.endswith(".app") for part in parts)


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
