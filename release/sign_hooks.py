"""Optional code-signing hooks for Release builds.

Sprint 2 decision
-----------------
**Unsigned builds** ship by default. Full Svarpy / Apple Developer ID and
Windows Authenticode signing without notarization is *possible* but not
low-complexity for CI (certs in GitHub Secrets, keychain import, entitlements,
``codesign --deep``, Windows signtool + certificate store). That setup is
deferred; these hooks stay so signing can be enabled later without rewriting
the pipeline.

Enable later
------------
1. Store certs/secrets in GitHub Actions (never commit them).
2. Set ``RESUME_WRITER_SIGN=1`` in the release workflow env.
3. Implement platform bodies in :func:`sign_macos` / :func:`sign_windows`.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path


def signing_enabled() -> bool:
    return os.environ.get("RESUME_WRITER_SIGN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def sign_macos(app_bundle: Path) -> None:
    """Sign a macOS ``.app`` with Developer ID (no notarization).

    Placeholder: requires ``APPLE_DEVELOPER_ID`` identity and optional
    ``APPLE_TEAM_ID`` / keychain secrets. Not implemented in Sprint 2.
    """
    identity = os.environ.get("APPLE_DEVELOPER_ID", "").strip()
    if not identity:
        raise RuntimeError(
            "RESUME_WRITER_SIGN is set but APPLE_DEVELOPER_ID is missing"
        )
    # Future:
    #   codesign --force --deep --options runtime
    #     --sign "$APPLE_DEVELOPER_ID" "path/to/App.app"
    raise NotImplementedError(
        f"macOS signing hook not implemented (would sign {app_bundle} as {identity})"
    )


def sign_windows(onedir: Path) -> None:
    """Authenticode-sign the Windows ``.exe`` inside an onedir build.

    Placeholder: requires ``WINDOWS_CERT_PFX`` / password secrets and signtool.
    Not implemented in Sprint 2.
    """
    if not os.environ.get("WINDOWS_CERT_PFX", "").strip():
        raise RuntimeError(
            "RESUME_WRITER_SIGN is set but WINDOWS_CERT_PFX is missing"
        )
    raise NotImplementedError(
        f"Windows signing hook not implemented (would sign exe under {onedir})"
    )


def maybe_sign_artifact(artifact: Path) -> None:
    """No-op unless ``RESUME_WRITER_SIGN`` is enabled."""
    if not signing_enabled():
        print("Signing skipped (RESUME_WRITER_SIGN unset; Sprint 2 ships unsigned).")
        return

    system = platform.system().lower()
    if system == "darwin":
        sign_macos(artifact)
    elif system == "windows" or os.name == "nt":
        sign_windows(artifact)
    else:
        print(f"Signing not supported on {system}; skipping.")
