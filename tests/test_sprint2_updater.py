"""Unit tests for in-app updater (mocked GitHub Releases API; no network)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure repo root is importable when tests live under tests/.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TEST_ROOT = tempfile.mkdtemp(prefix="rw-sprint2-updater-")
os.environ["RESUME_WRITER_DATA_DIR"] = _TEST_ROOT

from resume_writer.version import (  # noqa: E402
    asset_name_for_platform,
    compare_versions,
    macos_asset_name,
    normalize_version,
    version_is_newer,
    windows_asset_name,
)
from resume_writer.update.apply import (  # noqa: E402
    prepare_extracted_payload,
    replace_install,
)
from resume_writer.update.check import (  # noqa: E402
    UpdateCheckError,
    check_for_available_update,
    find_newer_release,
)
from resume_writer.update.download import verify_release_zip  # noqa: E402
from resume_writer.update.state import (  # noqa: E402
    is_check_due,
    load_state,
    record_check_now,
    save_state,
)


def _release(
    tag: str,
    *,
    assets: list | None = None,
    draft: bool = False,
    prerelease: bool = False,
    name: str = "",
) -> dict:
    return {
        "tag_name": tag,
        "name": name or tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": assets or [],
    }


def _asset(name: str, url: str, size: int = 10) -> dict:
    return {
        "name": name,
        "browser_download_url": url,
        "size": size,
    }


class VersionContractSmokeTests(unittest.TestCase):
    """Updater relies on shared ``resume_writer.version`` helpers from integ."""

    def test_asset_names_match_release_contract(self) -> None:
        self.assertEqual(normalize_version("3.0.0"), "v3.0.0")
        self.assertEqual(macos_asset_name("v3.1.0"), "ResumeWriterv3.1.0.app.zip")
        self.assertEqual(windows_asset_name("v3.1.0"), "ResumeWriterv3.1.0.exe.zip")
        self.assertEqual(
            asset_name_for_platform("v3.1.0", "darwin"),
            "ResumeWriterv3.1.0.app.zip",
        )
        self.assertEqual(
            asset_name_for_platform("v3.1.0", "win32"),
            "ResumeWriterv3.1.0.exe.zip",
        )

    def test_compare_versions(self) -> None:
        self.assertEqual(compare_versions("v3.0.0", "v3.0.0"), 0)
        self.assertTrue(version_is_newer("v3.1.0", "v3.0.0"))
        self.assertFalse(version_is_newer("v3.0.0", "v3.1.0"))
        self.assertTrue(version_is_newer("v3.0.0", "v3.0.0-beta"))
        self.assertFalse(version_is_newer("v2.9.9", "v3.0.0"))


class UpdateStateTests(unittest.TestCase):
    def setUp(self) -> None:
        save_state({})

    def test_check_due_when_never_checked(self) -> None:
        self.assertTrue(is_check_due())

    def test_not_due_within_week(self) -> None:
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        record_check_now(when=now)
        self.assertFalse(is_check_due(now=now + timedelta(days=3)))
        self.assertTrue(is_check_due(now=now + timedelta(days=7)))

    def test_record_persists(self) -> None:
        stamp = record_check_now(when=datetime(2026, 1, 1, tzinfo=timezone.utc))
        state = load_state()
        self.assertIn("last_check_at", state)
        self.assertEqual(stamp.year, 2026)


class MockResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            data = self._payload
            self._payload = b""
            return data
        data = self._payload[:n]
        self._payload = self._payload[n:]
        return data

    def __enter__(self) -> "MockResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


class UpdateCheckTests(unittest.TestCase):
    def test_find_newer_macos_asset(self) -> None:
        releases = [
            _release(
                "v3.0.0",
                assets=[_asset("ResumeWriterv3.0.0.app.zip", "https://example/old")],
            ),
            _release(
                "v3.2.0",
                assets=[
                    _asset("ResumeWriterv3.2.0.app.zip", "https://example/mac"),
                    _asset("ResumeWriterv3.2.0.exe.zip", "https://example/win"),
                ],
            ),
            _release(
                "v3.1.0",
                assets=[_asset("ResumeWriterv3.1.0.app.zip", "https://example/mid")],
            ),
        ]
        found = find_newer_release(releases, current_version="v3.0.0", platform="darwin")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.version, "v3.2.0")
        self.assertEqual(found.asset_name, "ResumeWriterv3.2.0.app.zip")
        self.assertEqual(found.download_url, "https://example/mac")

    def test_skips_draft_prerelease_and_missing_asset(self) -> None:
        releases = [
            _release(
                "v9.0.0",
                draft=True,
                assets=[_asset("ResumeWriterv9.0.0.app.zip", "https://example/d")],
            ),
            _release(
                "v8.0.0",
                prerelease=True,
                assets=[_asset("ResumeWriterv8.0.0.app.zip", "https://example/p")],
            ),
            _release(
                "v7.0.0",
                assets=[_asset("ResumeWriterv7.0.0.exe.zip", "https://example/wrong-os")],
            ),
        ]
        self.assertIsNone(
            find_newer_release(releases, current_version="v3.0.0", platform="darwin")
        )

    def test_check_for_available_update_uses_urlopen(self) -> None:
        payload = [
            _release(
                "v3.5.0",
                assets=[
                    _asset("ResumeWriterv3.5.0.app.zip", "https://example/a", size=42),
                    _asset("ResumeWriterv3.5.0.exe.zip", "https://example/e", size=43),
                ],
            )
        ]
        raw = json.dumps(payload).encode("utf-8")

        def fake_urlopen(request, *, timeout):  # noqa: ANN001
            self.assertIn("api.github.com", request.full_url)
            return MockResponse(raw)

        update = check_for_available_update(
            current_version="v3.0.0",
            platform="win32",
            urlopen=fake_urlopen,
        )
        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(update.asset_name, "ResumeWriterv3.5.0.exe.zip")
        self.assertEqual(update.size, 43)

    def test_network_error_raises_check_error(self) -> None:
        import urllib.error

        def boom(request, *, timeout):  # noqa: ANN001
            raise urllib.error.URLError("offline")

        with self.assertRaises(UpdateCheckError):
            check_for_available_update(urlopen=boom)


class UpdateApplyHelpersTests(unittest.TestCase):
    def test_verify_and_replace_macos_style(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_dir = root / "Resume Writer v3.1.0.app" / "Contents" / "MacOS"
            app_dir.mkdir(parents=True)
            (app_dir / "ResumeWriter").write_text("new", encoding="utf-8")

            zip_path = root / "ResumeWriterv3.1.0.app.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                for path in (root / "Resume Writer v3.1.0.app").rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(root).as_posix())

            self.assertEqual(verify_release_zip(zip_path, platform="darwin"), "app")

            install = root / "Install" / "Resume Writer.app"
            install.mkdir(parents=True)
            (install / "old.txt").write_text("old", encoding="utf-8")

            staging = root / "staging"
            staging.mkdir()
            with zipfile.ZipFile(zip_path, "r") as archive:
                archive.extractall(staging)
            payload = prepare_extracted_payload(staging, platform="darwin")
            final = replace_install(payload, install)
            self.assertEqual(final, install)
            self.assertTrue((install / "Contents" / "MacOS" / "ResumeWriter").is_file())
            self.assertFalse((install / "old.txt").exists())
            self.assertFalse(any(install.parent.glob("*.rw-backup*")))

    def test_replace_keeps_old_when_payload_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install = root / "AppDir"
            install.mkdir()
            (install / "keep.txt").write_text("keep", encoding="utf-8")
            missing = root / "does-not-exist"
            with self.assertRaises(Exception):
                replace_install(missing, install)
            self.assertTrue((install / "keep.txt").is_file())


class ManualUpdateCheckTests(unittest.TestCase):
    """Settings "Check for Updates" path ignores the weekly gate."""

    def setUp(self) -> None:
        save_state({})
        # Simulate a recent automatic check so is_check_due() is False.
        record_check_now(when=datetime(2026, 9, 23, tzinfo=timezone.utc))
        self.assertFalse(
            is_check_due(now=datetime(2026, 9, 24, tzinfo=timezone.utc))
        )

    def _fake_app(self):
        """Minimal stand-in with synchronous ``after`` and ``winfo_exists``."""

        class FakeApp:
            def __init__(self) -> None:
                self._pending: list = []

            def after(self, _ms, callback=None, *args):  # noqa: ANN001
                if callback is not None:
                    self._pending.append((callback, args))
                return None

            def winfo_exists(self) -> bool:
                return True

            def drain(self, *, rounds: int = 40) -> None:
                for _ in range(rounds):
                    if not self._pending:
                        return
                    callback, args = self._pending.pop(0)
                    callback(*args)

        return FakeApp()

    @staticmethod
    def _run_thread_inline():
        """Patch ``threading.Thread`` so ``start()`` runs the target immediately."""

        class ImmediateThread:
            def __init__(self, target=None, daemon=None, args=(), kwargs=None):  # noqa: ANN001
                self._target = target
                self._args = args or ()
                self._kwargs = kwargs or {}

            def start(self) -> None:
                if self._target is not None:
                    self._target(*self._args, **self._kwargs)

        return ImmediateThread

    def test_manual_check_up_to_date_ignores_weekly_gate(self) -> None:
        from resume_writer.update import service as update_service

        app = self._fake_app()
        infos: list[tuple[str, str]] = []

        with (
            unittest.mock.patch.object(
                update_service.threading,
                "Thread",
                self._run_thread_inline(),
            ),
            unittest.mock.patch.object(
                update_service,
                "check_for_available_update",
                return_value=None,
            ) as check_mock,
            unittest.mock.patch.object(
                update_service,
                "_show_info",
                side_effect=lambda _p, title, message: infos.append((title, message)),
            ),
            unittest.mock.patch.object(
                update_service,
                "_show_error",
                side_effect=lambda *_a, **_k: self.fail("unexpected error dialog"),
            ),
            unittest.mock.patch.object(
                update_service,
                "_handle_available_update",
                side_effect=lambda *_a, **_k: self.fail("unexpected install prompt"),
            ),
        ):
            update_service.manual_update_check(app)
            app.drain()

        check_mock.assert_called_once()
        self.assertEqual(len(infos), 1)
        self.assertIn("up to date", infos[0][0].lower())

    def test_manual_check_offers_install_when_update_available(self) -> None:
        from resume_writer.update import service as update_service
        from resume_writer.update.check import AvailableUpdate

        app = self._fake_app()
        update = AvailableUpdate(
            version="v9.9.9",
            tag_name="v9.9.9",
            asset_name="ResumeWriterv9.9.9.app.zip",
            download_url="https://example/u",
        )
        handled: list = []

        with (
            unittest.mock.patch.object(
                update_service.threading,
                "Thread",
                self._run_thread_inline(),
            ),
            unittest.mock.patch.object(
                update_service,
                "check_for_available_update",
                return_value=update,
            ),
            unittest.mock.patch.object(
                update_service,
                "_handle_available_update",
                side_effect=lambda _app, found: handled.append(found),
            ),
            unittest.mock.patch.object(
                update_service,
                "_show_info",
                side_effect=lambda *_a, **_k: self.fail("unexpected info dialog"),
            ),
            unittest.mock.patch.object(
                update_service,
                "_show_error",
                side_effect=lambda *_a, **_k: self.fail("unexpected error dialog"),
            ),
        ):
            update_service.manual_update_check(app)
            app.drain()

        self.assertEqual(handled, [update])

    def test_manual_check_shows_error_on_failure(self) -> None:
        from resume_writer.update import service as update_service
        from resume_writer.update.check import UpdateCheckError

        app = self._fake_app()
        errors: list[tuple[str, str]] = []

        with (
            unittest.mock.patch.object(
                update_service.threading,
                "Thread",
                self._run_thread_inline(),
            ),
            unittest.mock.patch.object(
                update_service,
                "check_for_available_update",
                side_effect=UpdateCheckError("offline"),
            ),
            unittest.mock.patch.object(
                update_service,
                "_show_error",
                side_effect=lambda _p, title, message: errors.append((title, message)),
            ),
            unittest.mock.patch.object(
                update_service,
                "_show_info",
                side_effect=lambda *_a, **_k: self.fail("unexpected info dialog"),
            ),
        ):
            update_service.manual_update_check(app)
            app.drain()

        self.assertEqual(len(errors), 1)
        self.assertIn("failed", errors[0][0].lower())
        self.assertIn("offline", errors[0][1])


if __name__ == "__main__":
    unittest.main()
