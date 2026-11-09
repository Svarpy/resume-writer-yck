"""Apply a downloaded release zip onto the installed app (safe replace)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

from resume_writer.update.download import updates_work_dir


class UpdateApplyError(Exception):
    """Install/replace failed; previous install should remain usable."""


def is_frozen_install() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve_install_target() -> Optional[Path]:
    """Return the install root to replace for a packaged build, else ``None``.

    - macOS: the ``Something.app`` bundle containing this executable
    - Windows (onedir): the folder containing the ``.exe``
    """
    if not is_frozen_install():
        return None
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in exe.parents:
            if parent.suffix == ".app" and parent.is_dir():
                return parent
        return None
    if sys.platform.startswith("win"):
        return exe.parent
    return None


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(dest_dir)
    return dest_dir


def _find_extracted_macos_app(root: Path) -> Path:
    apps = sorted(path for path in root.rglob("*.app") if path.is_dir())
    # Prefer shallowest .app (bundle root, not nested frameworks mistakenly named).
    if not apps:
        raise UpdateApplyError("Extracted update does not contain a .app bundle")
    apps.sort(key=lambda p: (len(p.parts), str(p)))
    return apps[0]


def _find_extracted_windows_payload(root: Path) -> Path:
    exes = sorted(
        path
        for path in root.rglob("*.exe")
        if path.is_file() and path.name.lower() != "uninstall.exe"
    )
    if not exes:
        raise UpdateApplyError("Extracted update does not contain an .exe")
    # Prefer an exe whose parent looks like an onedir folder (has other files).
    exes.sort(key=lambda p: (len(p.parts), str(p)))
    chosen = exes[0]
    return chosen.parent


def prepare_extracted_payload(staging_dir: Path, *, platform: Optional[str] = None) -> Path:
    plat = (platform or sys.platform).lower()
    if plat in ("darwin", "macos", "mac"):
        return _find_extracted_macos_app(staging_dir)
    if plat.startswith("win"):
        return _find_extracted_windows_payload(staging_dir)
    raise UpdateApplyError(f"Unsupported platform for apply: {plat!r}")


def _unique_backup_path(target: Path) -> Path:
    candidate = target.with_name(target.name + ".rw-backup")
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = target.with_name(f"{target.name}.rw-backup-{index}")
        if not candidate.exists():
            return candidate
        index += 1


def replace_install(new_payload: Path, install_target: Path) -> Path:
    """Replace ``install_target`` with ``new_payload``, keeping old until success.

    Strategy:
    1. Move current install aside to a backup name (if it exists).
    2. Move new payload into the final location (same parent as old target when
       possible; otherwise into ``install_target``'s parent using the new name).
    3. On failure, restore the backup.
    4. On success, delete the backup.
    """
    install_target = Path(install_target)
    new_payload = Path(new_payload)
    if not new_payload.exists():
        raise UpdateApplyError(f"New install payload missing: {new_payload}")

    parent = install_target.parent
    parent.mkdir(parents=True, exist_ok=True)

    # Final destination: keep the existing install path/name when possible so
    # shortcuts and Dock entries keep working. For macOS .app, rename the new
    # bundle to match the old bundle name after staging.
    final_path = install_target
    backup: Optional[Path] = None

    try:
        if install_target.exists():
            backup = _unique_backup_path(install_target)
            install_target.rename(backup)

        # Place new payload at final_path. If names differ (versioned .app),
        # move/rename into final_path.
        if new_payload.resolve() != final_path.resolve():
            if final_path.exists():
                raise UpdateApplyError(f"Install path still occupied: {final_path}")
            # Cross-device safe: copytree then remove source when rename fails.
            try:
                new_payload.rename(final_path)
            except OSError:
                if new_payload.is_dir():
                    shutil.copytree(new_payload, final_path)
                    shutil.rmtree(new_payload, ignore_errors=True)
                else:
                    shutil.copy2(new_payload, final_path)
                    new_payload.unlink(missing_ok=True)
    except Exception as exc:
        # Restore previous install if we moved it aside.
        if backup is not None and backup.exists() and not install_target.exists():
            try:
                backup.rename(install_target)
            except OSError:
                pass
        if isinstance(exc, UpdateApplyError):
            raise
        raise UpdateApplyError(f"Failed to replace install: {exc}") from exc

    if backup is not None and backup.exists():
        try:
            if backup.is_dir():
                shutil.rmtree(backup)
            else:
                backup.unlink()
        except OSError:
            # Non-fatal: leftover backup is preferable to a broken restore.
            pass

    return final_path


def apply_update_zip(
    zip_path: Path,
    *,
    install_target: Optional[Path] = None,
    platform: Optional[str] = None,
) -> Path:
    """Extract, verify payload, replace install. Old install kept until success."""
    target = install_target if install_target is not None else resolve_install_target()
    if target is None:
        raise UpdateApplyError(
            "Updates can only be applied to a packaged Resume Writer install "
            "(not a source/development run)."
        )

    work = updates_work_dir()
    staging = work / "staging"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        extract_zip(zip_path, staging)
        payload = prepare_extracted_payload(staging, platform=platform)
        return replace_install(payload, target)
    except UpdateApplyError:
        raise
    except Exception as exc:
        raise UpdateApplyError(f"Could not apply update: {exc}") from exc
    finally:
        # Staging leftovers cleaned by cleanup_update_files; keep on failure for debug?
        # Spec: cleanup update files after success. On failure keep previous install;
        # still remove staging to avoid disk clutter.
        shutil.rmtree(staging, ignore_errors=True)


def cleanup_update_files(*paths: Path) -> None:
    work = updates_work_dir()
    for path in paths:
        if path is None:
            continue
        p = Path(path)
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except OSError:
            pass
    # Remove empty updates dir members we own.
    staging = work / "staging"
    shutil.rmtree(staging, ignore_errors=True)


def launch_installed_app(install_path: Path) -> None:
    """Start the newly installed app (caller should exit afterward)."""
    install_path = Path(install_path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(install_path)], close_fds=True)
        return
    if sys.platform.startswith("win"):
        exe_candidates = sorted(install_path.glob("*.exe"))
        if install_path.is_file() and install_path.suffix.lower() == ".exe":
            exe = install_path
        elif exe_candidates:
            # Prefer non-uninstall binaries and names containing Resume.
            preferred = [
                p
                for p in exe_candidates
                if "uninstall" not in p.name.lower()
            ]
            preferred.sort(
                key=lambda p: (0 if "resume" in p.name.lower() else 1, p.name.lower())
            )
            exe = preferred[0] if preferred else exe_candidates[0]
        else:
            raise UpdateApplyError(f"No executable found under {install_path}")
        subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
        return
    raise UpdateApplyError(f"Unsupported platform for relaunch: {sys.platform}")


def relaunch_and_exit(install_path: Path, *, exit_fn=None) -> None:
    launch_installed_app(install_path)
    closer = exit_fn or os._exit
    closer(0)
