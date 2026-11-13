"""Generate a resume from a template: the one call the rest of the application uses."""

from __future__ import annotations

from pathlib import Path

from resume_core.placeholders.content import build_data
from resume_core.placeholders.fill import fill_template
from resume_core.placeholders.info import TemplateError, inspect_template


def build_resume(content, fmt, output_path: Path) -> Path:
    """Fill the format's template (``fmt.template_path``) with ``content`` and save it to ``output_path``."""
    from resume_core.render.parse import split_keywords

    template = Path(fmt.template_path) if fmt.template_path else None
    if template is None or not template.is_file():
        raise TemplateError("No resume format is available. Upload a template document first.")
    info = inspect_template(template.read_bytes())
    if not info.ok:
        raise TemplateError("The resume format has problems: " + "; ".join(info.errors))
    unplaced = [spec for spec in content.section_plan
                if spec.kind not in ("education", "keywords") and spec.key not in info.shape
                and (content.text_for(spec.key) or "").strip()]
    if unplaced:
        raise TemplateError(
            "The resume format has no place for: " + ", ".join(spec.label or spec.key for spec in unplaced)
            + ". Add {{#" + unplaced[0].key + "}} ... {{/" + unplaced[0].key + "}} to the template, "
            "or switch the section off in Settings.")
    data = build_data(content, info.shape)
    name = content.name.strip()
    properties = {
        "author": content.author.strip(),            # empty stays empty: no property is invented
        "subject": content.subject.strip(),
        "keywords": ", ".join(split_keywords(content.keyword_source(), content.keyword_count)),
        "title": content.title_template.replace("{name}", name).strip(),
        "last_modified_by": content.author.strip(),
    }
    return fill_template(template, data, output_path, font_name=fmt.font_name, name_size=fmt.name_size,
                         heading_size=fmt.heading_size, body_size=fmt.body_size, properties=properties,
                         headings=_heading_choices(content, info))


def _heading_choices(content, info) -> dict[str, tuple[str, bool]]:
    """Headings the user changed in Settings (text or hidden); the template's own text is the default."""
    own = {row["key"]: row["heading"] for row in info.sections}
    out: dict[str, tuple[str, bool]] = {}
    for spec in content.section_plan:
        template_heading = own.get(spec.key)
        if not template_heading:
            continue                      # the template shows no heading for this section
        text = (spec.heading or "").strip()
        shown = bool(getattr(spec, "show_heading", True))
        if (text and text != template_heading) or not shown:
            out[spec.key] = (text if text != template_heading else "", shown)
    return out
