"""Orchestrate launch-time update checks and Install Now / Remind Later UX."""

from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

from resume_writer.constants import APP_VERSION
from resume_writer.update.apply import (
    UpdateApplyError,
    apply_update_zip,
    cleanup_update_files,
    relaunch_and_exit,
)
from resume_writer.update.check import (
    AvailableUpdate,
    UpdateCheckError,
    check_for_available_update,
)
from resume_writer.update.download import (
    UpdateDownloadError,
    download_asset,
    updates_work_dir,
    verify_release_zip,
)
from resume_writer.update.state import is_check_due, record_check_now


def prompt_install_or_later(parent: Any, update: AvailableUpdate) -> str:
    """Show Install Now / Remind Later. Returns ``install`` or ``later``."""
    import tkinter as tk

    choice = {"value": "later"}
    dialog = tk.Toplevel(parent)
    dialog.title("Update Available")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.resizable(False, False)

    frame = tk.Frame(dialog, padx=20, pady=16)
    frame.pack(fill=tk.BOTH, expand=True)

    message = (
        f"Resume Writer {update.version} is available.\n"
        f"You are currently on {APP_VERSION}.\n\n"
        "Install now? The app will download the update, replace this install, "
        "and relaunch."
    )
    tk.Label(frame, text=message, justify=tk.LEFT, wraplength=420).pack(anchor="w")

    buttons = tk.Frame(frame)
    buttons.pack(fill=tk.X, pady=(16, 0))

    def choose(value: str) -> None:
        choice["value"] = value
        dialog.destroy()

    later_btn = tk.Button(buttons, text="Remind Later", command=lambda: choose("later"))
    later_btn.pack(side=tk.RIGHT, padx=(8, 0))
    install_btn = tk.Button(buttons, text="Install Now", command=lambda: choose("install"))
    install_btn.pack(side=tk.RIGHT)

    dialog.protocol("WM_DELETE_WINDOW", lambda: choose("later"))
    dialog.update_idletasks()
    try:
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        w = dialog.winfo_reqwidth()
        h = dialog.winfo_reqheight()
        dialog.geometry(f"+{parent_x + max(0, (parent_w - w) // 2)}+{parent_y + max(0, (parent_h - h) // 3)}")
    except tk.TclError:
        pass

    parent.wait_window(dialog)
    return choice["value"]


def run_install_now(
    update: AvailableUpdate,
    *,
    progress_cb: Optional[Callable[[str], None]] = None,
    platform: Optional[str] = None,
) -> Path:
    """Download → verify → apply → cleanup. Raises on failure (old install kept)."""

    def note(msg: str) -> None:
        if progress_cb is not None:
            progress_cb(msg)

    work = updates_work_dir()
    zip_path = work / update.asset_name
    note("Downloading update…")
    download_asset(
        update.download_url,
        zip_path,
        expected_size=update.size,
    )
    note("Verifying update…")
    verify_release_zip(zip_path, platform=platform)
    note("Installing update…")
    try:
        installed = apply_update_zip(zip_path, platform=platform)
    except UpdateApplyError:
        # Keep zip for a manual retry? Spec: cleanup after update; on failure
        # keep previous install — remove partial staging (apply already does).
        raise
    note("Cleaning up…")
    cleanup_update_files(zip_path)
    record_check_now()
    return installed


def _show_error(parent: Any, title: str, message: str) -> None:
    try:
        from tkinter import messagebox

        messagebox.showerror(title, message, parent=parent)
    except Exception:
        pass


def _show_info(parent: Any, title: str, message: str) -> None:
    try:
        from tkinter import messagebox

        messagebox.showinfo(title, message, parent=parent)
    except Exception:
        pass


def _handle_available_update(app: Any, update: AvailableUpdate) -> None:
    choice = prompt_install_or_later(app, update)
    if choice != "install":
        record_check_now()
        return

    status = {"text": "Starting update…"}

    def progress(msg: str) -> None:
        status["text"] = msg

    # Simple blocking progress dialog on the UI thread via after-polling would
    # be nicer; keep Sprint 2 lean: run install on a worker and show result.
    busy = {"done": False, "error": None, "installed": None}

    def worker() -> None:
        try:
            busy["installed"] = run_install_now(update, progress_cb=progress)
        except (UpdateDownloadError, UpdateApplyError, OSError) as exc:
            busy["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 — fail soft, keep old install
            busy["error"] = str(exc)
            traceback.print_exc()
        finally:
            busy["done"] = True

    threading.Thread(target=worker, daemon=True).start()

    progress_win = None
    try:
        import tkinter as tk

        progress_win = tk.Toplevel(app)
        progress_win.title("Updating Resume Writer")
        progress_win.transient(app)
        progress_win.grab_set()
        progress_win.resizable(False, False)
        label = tk.Label(progress_win, text=status["text"], padx=24, pady=20, width=40)
        label.pack()
        progress_win.protocol("WM_DELETE_WINDOW", lambda: None)

        def poll() -> None:
            if progress_win is not None:
                try:
                    label.configure(text=status["text"])
                except tk.TclError:
                    pass
            if not busy["done"]:
                app.after(200, poll)
                return
            if progress_win is not None:
                try:
                    progress_win.grab_release()
                    progress_win.destroy()
                except tk.TclError:
                    pass
            if busy["error"]:
                _show_error(
                    app,
                    "Update failed",
                    f"Could not install the update. Your previous install was kept.\n\n{busy['error']}",
                )
                return
            installed = busy["installed"]
            _show_info(
                app,
                "Update installed",
                f"Resume Writer {update.version} was installed.\nThe app will relaunch now.",
            )
            try:
                relaunch_and_exit(installed)
            except Exception as exc:  # noqa: BLE001
                _show_error(
                    app,
                    "Relaunch failed",
                    f"Update files were installed but relaunch failed:\n{exc}\n"
                    "Please quit and open Resume Writer again.",
                )

        app.after(200, poll)
    except Exception as exc:  # noqa: BLE001
        if progress_win is not None:
            try:
                progress_win.destroy()
            except Exception:
                pass
        _show_error(app, "Update failed", str(exc))


def schedule_launch_update_check(app: Any, *, delay_ms: int = 900) -> None:
    """After auth / main shell is ready: weekly GitHub Releases check (fail soft)."""

    if getattr(app, "_rw_update_check_scheduled", False):
        return
    app._rw_update_check_scheduled = True

    def start() -> None:
        thread = threading.Thread(target=_background_check, args=(app,), daemon=True)
        thread.start()

    try:
        app.after(delay_ms, start)
    except Exception:
        # If Tk is already gone, skip quietly.
        return


def _background_check(app: Any) -> None:
    try:
        if not is_check_due():
            return
        update = check_for_available_update()
    except UpdateCheckError:
        # Network / API errors: fail soft, do not advance last-check (retry next launch).
        return
    except Exception:
        traceback.print_exc()
        return

    if update is None:
        try:
            record_check_now()
        except Exception:
            pass
        return

    def on_main() -> None:
        try:
            if not app.winfo_exists():
                return
            _handle_available_update(app, update)
        except Exception:
            traceback.print_exc()

    try:
        app.after(0, on_main)
    except Exception:
        return
