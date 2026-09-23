"""Build PyInstaller onedir bundles and zip them for GitHub Releases.

Usage (from repo root, with deps installed)::

    python release/build_release.py          # build + zip for this OS
    python release/build_release.py --zip-only
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resume_writer.version import (  # noqa: E402
    APP_VERSION,
    compact_version_slug,
    display_name,
    macos_asset_name,
    pyinstaller_name,
    windows_asset_name,
)


DOC_SRC = ROOT / "resume_writer" / "docs" / "documentation.md"
DIST = ROOT / "dist"
RELEASE_OUT = ROOT / "release" / "out"


def _is_windows() -> bool:
    return os.name == "nt" or platform.system().lower().startswith("win")


def _bundle_name() -> str:
    """PyInstaller --name: human title on macOS; compact slug on Windows."""
    if _is_windows():
        return compact_version_slug()
    return pyinstaller_name()


def _add_data_arg() -> str:
    sep = ";" if _is_windows() else ":"
    return f"{DOC_SRC}{sep}resume_writer/docs"


def run_pyinstaller() -> Path:
    """Run PyInstaller onedir/windowed build; return the primary artifact path."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:  # pragma: no cover - CI installs deps
        raise SystemExit(
            "PyInstaller is required. Install with: pip install -r requirements.txt"
        ) from exc

    if not DOC_SRC.is_file():
        raise SystemExit(f"Missing documentation data file: {DOC_SRC}")

    name = _bundle_name()
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(ROOT / "resume_writer_app.py"),
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        f"--name={name}",
        f"--add-data={_add_data_arg()}",
        f"--distpath={DIST}",
        f"--workpath={ROOT / 'build'}",
        f"--specpath={ROOT / 'build'}",
        "--hidden-import=bcrypt",
        "--hidden-import=docx",
    ]
    print(f"Building {name!r} (APP_VERSION={APP_VERSION}) …", flush=True)
    print("PyInstaller cmd:", cmd, flush=True)
    completed = subprocess.run(cmd, cwd=str(ROOT), check=False)
    if completed.returncode != 0:
        raise SystemExit(f"PyInstaller failed with exit code {completed.returncode}")

    system = platform.system().lower()
    if system == "darwin":
        app_path = DIST / f"{name}.app"
        if not app_path.is_dir():
            raise SystemExit(f"Expected macOS app bundle missing: {app_path}")
        return app_path

    folder = DIST / name
    if not folder.is_dir():
        listing = (
            ", ".join(sorted(p.name for p in DIST.iterdir())) if DIST.is_dir() else "(no dist/)"
        )
        raise SystemExit(
            f"Expected onedir folder missing: {folder}; dist contains: {listing}"
        )
    return folder


def _zip_tree(source: Path, dest_zip: Path) -> None:
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    if dest_zip.exists():
        dest_zip.unlink()
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if source.is_file():
            zf.write(source, arcname=source.name)
            return
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(source.parent)))


def zip_artifact(artifact: Path | None = None) -> Path:
    """Zip the built artifact into the Release asset name for this OS."""
    system = platform.system().lower()
    RELEASE_OUT.mkdir(parents=True, exist_ok=True)
    name = _bundle_name()

    if system == "darwin":
        source = artifact or (DIST / f"{name}.app")
        dest = RELEASE_OUT / macos_asset_name()
    elif _is_windows():
        source = artifact or (DIST / name)
        dest = RELEASE_OUT / windows_asset_name()
    else:
        source = artifact or (DIST / name)
        dest = RELEASE_OUT / f"{windows_asset_name().replace('.exe.zip', '.linux.zip')}"

    if not source.exists():
        raise SystemExit(f"Nothing to zip; missing {source}")

    print(f"Zipping {source} → {dest}", flush=True)
    _zip_tree(source, dest)
    return dest


def maybe_sign(artifact: Path) -> None:
    """Invoke optional signing hooks when enabled (default: skip)."""
    from release.sign_hooks import maybe_sign_artifact

    maybe_sign_artifact(artifact)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--zip-only",
        action="store_true",
        help="Skip PyInstaller; zip an existing dist artifact",
    )
    parser.add_argument(
        "--print-names",
        action="store_true",
        help="Print version and asset names, then exit",
    )
    args = parser.parse_args(argv)

    if args.print_names:
        print(f"APP_VERSION={APP_VERSION}")
        print(f"display_name={display_name()}")
        print(f"bundle_name={_bundle_name()}")
        print(f"macos_asset={macos_asset_name()}")
        print(f"windows_asset={windows_asset_name()}")
        return 0

    if args.zip_only:
        zip_artifact()
        return 0

    artifact = run_pyinstaller()
    maybe_sign(artifact)
    zip_artifact(artifact)
    print(f"Done. Display name: {display_name()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
