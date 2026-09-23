"""Public resume generation API."""

from __future__ import annotations

from pathlib import Path

from resume_writer.render.heuristic import _build_resume_heuristic
from resume_writer.render.models import ResumeContent, ResumeFormat


def build_resume(content: ResumeContent, fmt: ResumeFormat, output_path: Path) -> Path:
    """Generate a resume DOCX.

    When ``fmt.template_path`` points at a preserved uploaded template, clone that
    package and inject Writer content. Otherwise use the historical default path.
    """
    if fmt.template_path and Path(fmt.template_path).is_file():
        from resume_writer.render.template import build_resume_from_template

        return build_resume_from_template(content, fmt, output_path)
    return _build_resume_heuristic(content, fmt, output_path)
