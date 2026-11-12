"""Resume DOCX rendering."""

from __future__ import annotations

from resume_core.placeholders import TemplateError
from resume_core.render.api import build_resume
from resume_core.render.models import ResumeContent, ResumeFormat, SectionSpec
from resume_core.render.parse import (
    build_output_filename,
    count_words,
    default_output_filename,
    default_output_filename_for,
    find_duplicate_files,
    split_keywords,
)

__all__ = [
    "ResumeContent",
    "ResumeFormat",
    "SectionSpec",
    "TemplateError",
    "build_output_filename",
    "build_resume",
    "count_words",
    "default_output_filename",
    "default_output_filename_for",
    "find_duplicate_files",
    "split_keywords",
]
