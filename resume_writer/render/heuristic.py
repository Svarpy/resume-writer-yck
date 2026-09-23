"""Heuristic (non-template) resume body population and section renderers."""

from __future__ import annotations

from pathlib import Path

from formats_store import default_document_structure

from resume_writer.constants import AUTHOR_NAME, EMAIL, LOCATION, PHONE
from resume_writer.render import docx_ops
from resume_writer.render.docx_ops import (
    add_border_rule,
    add_education_entry,
    add_experience_section,
    add_hyperlink,
    add_multiline_section,
    add_section_heading,
    add_text_run,
    apply_document_defaults,
    format_paragraph,
    load_docx_dependencies,
    set_run_font,
    _alignment_from_name,
)
from resume_writer.render.models import ResumeContent, ResumeFormat
from resume_writer.render.parse import clean_lines, phone_hyperlink


def _build_resume_heuristic(content: ResumeContent, fmt: ResumeFormat, output_path: Path) -> Path:
    load_docx_dependencies()
    document = docx_ops.Document()
    apply_document_defaults(document, fmt)
    _populate_resume_body_for_template(document, content, fmt, prototypes=None)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    return output_path


def _populate_resume_body_for_template(document, content: ResumeContent, fmt: ResumeFormat, *, prototypes=None) -> None:
    """Shared body writer used by heuristic and template-preserving generate paths."""
    from resume_writer.render.template import clone_heading, clone_separator

    structure = fmt.structure or default_document_structure()

    name_paragraph = document.add_paragraph()
    format_paragraph(
        name_paragraph,
        before=0,
        after=3,
        alignment=_alignment_from_name(structure.name_alignment),
        line_spacing=fmt.line_spacing,
    )
    name_run = name_paragraph.add_run(content.name or AUTHOR_NAME)
    set_run_font(name_run, fmt.font_name, fmt.name_size, bold=True)

    contact = document.add_paragraph()
    format_paragraph(
        contact,
        before=0,
        after=3,
        alignment=_alignment_from_name(structure.contact_alignment),
        line_spacing=fmt.line_spacing,
    )
    email = content.email or EMAIL
    phone = content.phone or PHONE
    location = content.location or LOCATION
    sep = structure.contact_separator or "  |  "
    add_hyperlink(contact, email, f"mailto:{email}", fmt)
    add_text_run(contact, sep, fmt, bold=True)
    add_hyperlink(contact, phone, phone_hyperlink(phone), fmt)
    add_text_run(contact, sep, fmt, bold=True)
    add_text_run(contact, location, fmt)

    section_renderers = {
        "summary": lambda: _render_summary_section(document, content, fmt),
        "skills": lambda: _render_skills_section(document, content, fmt),
        "experience": lambda: _render_experience_section(document, content, fmt),
        "education": lambda: _render_education_section(document, content, fmt),
        "certifications": lambda: _render_certifications_section(document, content, fmt),
    }

    for key in structure.ordered_content_keys():
        renderer = section_renderers.get(key)
        if renderer is None:
            continue
        if key == "education" and not content.education_entries:
            continue
        if key == "certifications" and not content.certifications.strip():
            continue
        rule = structure.section_for(key)
        heading = rule.heading if rule is not None else key.upper()
        separator_before = rule.separator_before if rule is not None else True
        if separator_before and structure.separator.enabled:
            if prototypes is not None:
                clone_separator(document, prototypes, fmt)
            else:
                add_border_rule(document, fmt)
        if prototypes is not None:
            clone_heading(document, heading, prototypes, fmt)
        else:
            add_section_heading(document, heading, fmt)
        renderer()



def _render_summary_section(document: Document, content: ResumeContent, fmt: ResumeFormat) -> None:
    add_multiline_section(document, clean_lines(content.summary), fmt, paragraph_alignment=docx_ops.WD_ALIGN_PARAGRAPH.JUSTIFY)


def _render_skills_section(document: Document, content: ResumeContent, fmt: ResumeFormat) -> None:
    add_multiline_section(
        document,
        clean_lines(content.skills),
        fmt,
        skill_mode=True,
        paragraph_alignment=docx_ops.WD_ALIGN_PARAGRAPH.LEFT,
    )


def _render_experience_section(document: Document, content: ResumeContent, fmt: ResumeFormat) -> None:
    add_experience_section(document, clean_lines(content.experience), fmt)


def _render_education_section(document: Document, content: ResumeContent, fmt: ResumeFormat) -> None:
    for education_entry in content.education_entries:
        add_education_entry(document, education_entry, fmt)


def _render_certifications_section(document: Document, content: ResumeContent, fmt: ResumeFormat) -> None:
    add_multiline_section(
        document,
        clean_lines(content.certifications),
        fmt,
        paragraph_alignment=docx_ops.WD_ALIGN_PARAGRAPH.LEFT,
    )
