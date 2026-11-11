"""Public resume generation API."""

from __future__ import annotations

from pathlib import Path

from resume_core.render.models import ResumeContent, ResumeFormat
from resume_core.render.template import TemplateGenerationError, build_resume_from_template


def build_resume(content: ResumeContent, fmt: ResumeFormat, output_path: Path) -> Path:
    """Generate a resume DOCX from the format's sample document."""
    if not fmt.template_path or not Path(fmt.template_path).is_file():
        raise TemplateGenerationError("No resume format is available. Upload a sample document first.")
    return build_resume_from_template(content, fmt, output_path)
