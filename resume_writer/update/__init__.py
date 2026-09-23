"""In-app auto-updater: check GitHub Releases, download, apply, relaunch."""

from __future__ import annotations

from resume_writer.update.check import AvailableUpdate, check_for_available_update
from resume_writer.update.service import (
    run_install_now,
    schedule_launch_update_check,
)
from resume_writer.update.state import (
    CHECK_INTERVAL_DAYS,
    is_check_due,
    record_check_now,
)

__all__ = [
    "AvailableUpdate",
    "CHECK_INTERVAL_DAYS",
    "check_for_available_update",
    "is_check_due",
    "record_check_now",
    "run_install_now",
    "schedule_launch_update_check",
]
