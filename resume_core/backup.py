"""Backup file naming."""

from __future__ import annotations

from datetime import date
from typing import Optional

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def backup_basename(day: Optional[date] = None) -> str:
    """``ResWritBkpYYYYMMMDD`` with a three-letter English month, e.g. ``ResWritBkp2026Nov11``."""
    day = day or date.today()
    return f"ResWritBkp{day.year:04d}{MONTHS[day.month - 1]}{day.day:02d}"
