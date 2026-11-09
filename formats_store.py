"""Compat shim — prefer ``resume_writer.formats``."""

from __future__ import annotations

from resume_writer.formats import *  # noqa: F403
from resume_writer.formats import __all__  # noqa: F401
