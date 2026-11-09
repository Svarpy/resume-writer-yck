"""Thin entrypoint and compat re-exports for Resume Writer.

Prefer::

    python -m resume_writer
    python3 resume_writer_app.py
"""

from __future__ import annotations

import os

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

# Compat re-exports expected by tests and older imports.
from resume_writer.constants import *  # noqa: F401,F403
from resume_writer.render.api import build_resume  # noqa: F401
from resume_writer.render.docx_ops import load_docx_dependencies  # noqa: F401
from resume_writer.render.models import (  # noqa: F401
    ResumeContent,
    ResumeFormat,
    resume_format_from_store,
)
from resume_writer.render.parse import (  # noqa: F401
    count_words,
    default_output_filename,
    default_output_filename_for,
    find_matching_output_files,
    split_keywords,
)
from resume_writer.ui.app import ResumeWriterApp  # noqa: F401


def main() -> None:
    ResumeWriterApp().mainloop()


if __name__ == "__main__":
    main()
