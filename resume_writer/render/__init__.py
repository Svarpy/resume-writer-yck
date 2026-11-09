"""Resume DOCX rendering."""

from __future__ import annotations

from resume_writer.render.api import build_resume
from resume_writer.render.models import ResumeContent, ResumeFormat, resume_format_from_store
from resume_writer.render.parse import (
    count_words,
    default_output_filename,
    default_output_filename_for,
    find_matching_output_files,
    split_keywords,
)

__all__ = [
    "ResumeContent",
    "ResumeFormat",
    "build_resume",
    "count_words",
    "default_output_filename",
    "default_output_filename_for",
    "find_matching_output_files",
    "resume_format_from_store",
    "split_keywords",
]
