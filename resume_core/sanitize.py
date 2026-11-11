"""Remove the sample author's personal content from an uploaded format before it is stored.

Instead of blanking text (which would break the parser: it recognises headings, dates, skill labels and
contact items by their text), the sample is regenerated through our own generator with neutral
placeholder content. Every format property (styles, numbering, tabs, tables, columns, headers/footers)
is kept; only the text changes. The result is re-analysed and accepted only if it describes the same
sections as the original, so sanitising can never change how a format behaves.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

from docx import Document

from resume_core.ooxml.analysis import DocumentAnalysis, analyze_document
from resume_core.render.models import ResumeContent, ResumeFormat, SectionSpec
from resume_core.render.template import build_resume_from_template

PLACEHOLDER_NAME = "Your Name"
PLACEHOLDER_TAGLINE = "Your Tagline"
PLACEHOLDER_EMAIL = "your.name@example.com"
PLACEHOLDER_PHONE = "+1 555 010 0100"
PLACEHOLDER_LOCATION = "City, State"

_PARAGRAPH = "This is sample text that shows how a paragraph of your resume will look."
_SKILLS = ("Category One: item one, item two, item three\nCategory Two: item four, item five\n"
           "Category Three: item six, item seven\nCategory Four: item eight, item nine")
_EXPERIENCE = (
    "Company Name | Location\tJanuary 2020 – Present\nSoftware Engineer\tJanuary 2020 – Present\n"
    "- Sample bullet point describing an achievement.\n- Another sample bullet point about your work.\n"
    "Company Name | Location\tJanuary 2018 – December 2019\nSoftware Engineer\tJanuary 2018 – December 2019\n"
    "- Sample bullet point describing an achievement.\n- Another sample bullet point about your work."
)
_BULLETS = "- Sample bullet point describing an item.\n- Another sample bullet point for this section."
_EDUCATION = ("Degree Name\tJanuary 2016 – May 2020\nInstitution Name, City, State\n\n"
              "Degree Name\tJanuary 2014 – May 2016\nInstitution Name, City, State")
_TEXT_BY_KIND = {"paragraph": _PARAGRAPH, "skills": _SKILLS, "experience": _EXPERIENCE, "bullets": _BULLETS}


def _structure(analysis: DocumentAnalysis) -> list[tuple[str, str, str]]:
    return [(r.key, r.kind, r.heading_text) for r in analysis.regions]


def _placeholder_content(analysis: DocumentAnalysis) -> ResumeContent:
    plan, texts = [], {}
    for region in analysis.regions:
        plan.append(SectionSpec(region.key, region.heading_text or region.key, region.kind))
        if region.kind != "education":
            texts[region.key] = _TEXT_BY_KIND.get(region.kind, _PARAGRAPH)
    return ResumeContent(
        name=PLACEHOLDER_NAME, email=PLACEHOLDER_EMAIL, phone=PLACEHOLDER_PHONE, location=PLACEHOLDER_LOCATION,
        tagline=PLACEHOLDER_TAGLINE if analysis.tagline is not None else "",
        sections=texts, section_plan=tuple(plan),
        education_entries=(_EDUCATION,) if any(r.kind == "education" for r in analysis.regions) else (),
        author="", subject="", title_template="Resume", keyword_count=0,
    )


def _clear_properties(document) -> None:
    core = document.core_properties
    core.author = core.last_modified_by = core.comments = core.keywords = core.subject = core.category = ""
    core.title = "Resume"


def sanitize_sample(data: bytes) -> tuple[bytes, bool]:
    """Return ``(sample without personal text, True)``, or ``(data, False)`` when it cannot be done safely."""
    try:
        original = analyze_document(Document(io.BytesIO(data)))
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder, "in.docx"), Path(folder, "out.docx")
            source.write_bytes(data)
            build_resume_from_template(_placeholder_content(original), ResumeFormat(template_path=source), target)
            document = Document(str(target))
            _clear_properties(document)
            buffer = io.BytesIO()
            document.save(buffer)
        cleaned = buffer.getvalue()
        if _structure(analyze_document(Document(io.BytesIO(cleaned)))) != _structure(original):
            return data, False  # sanitising would change how the format behaves: keep the original
        return cleaned, True
    except Exception:  # noqa: BLE001 - never block an upload because sanitising failed
        return data, False
