"""ResumeWriter application package."""

from __future__ import annotations

from resume_writer.constants import APP_VERSION

__all__ = ["__version__", "APP_VERSION"]

# Single source of truth: resume_writer.constants.APP_VERSION
__version__ = APP_VERSION
