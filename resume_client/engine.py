"""Local resume generation: validation, output path, duplicate check and writing the document.

Everything here runs on the user's machine and works on plain data (a ``Settings`` object, the format
info and the template's local path), so the desktop app and the MCP server share exactly the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from resume_client.client import ResumeClient
from resume_client.errors import ClientError, NoFormatError
from resume_core.render import (
    ResumeContent,
    ResumeFormat,
    SectionSpec,
    build_output_filename,
    build_resume,
    count_words,
    find_duplicate_files,
)
from resume_core.settings import FILE_NAME_FIELD, Settings


class GenerationError(ClientError):
    """The resume could not be generated; the message says why."""


@dataclass
class WriterContext:
    """Everything needed to write a resume: settings, the default format and its local template."""

    settings: Settings
    format_info: dict[str, Any]
    sample_path: Path
    username: str

    @property
    def format_id(self) -> str:
        return self.format_info["id"]


def load_context(client: ResumeClient) -> WriterContext:
    """Fetch (from cache when possible) the settings, default format and template for the signed-in user."""
    info = client.default_format()
    if not info:
        raise NoFormatError("No resume format yet. Upload a template document first.")
    return WriterContext(client.settings().settings(), info, client.sample_path(), client.username)


# -- output path and duplicates -----------------------------------------------------------------
def output_directory(settings: Settings) -> Path:
    return Path(settings.get("output.directory")).expanduser()


def output_filename(settings: Settings, company: str, username: str) -> str:
    return build_output_filename(
        company,
        template=settings.get("output.filename_template"),
        placeholder=settings.get("output.company_placeholder"),
        date_format=settings.get("output.date_format"),
        name=settings.get("personal.name"),
        username=username,
    )


def output_path(settings: Settings, company: str, username: str) -> Path:
    return output_directory(settings) / output_filename(settings, company, username)


def duplicate_files(settings: Settings, company: str) -> list[Path]:
    """Existing files that clash with ``company`` (empty when the duplicate check is switched off)."""
    if not settings.get("duplicate_check.enabled"):
        return []
    directory = str(output_directory(settings))
    folders = [Path(entry.replace("{output_dir}", directory)).expanduser()
               for entry in settings.get("duplicate_check.directories")]
    return find_duplicate_files(
        folders, company,
        extensions=settings.get("duplicate_check.extensions"),
        case_sensitive=settings.get("duplicate_check.case_sensitive"),
    )


# -- validation ---------------------------------------------------------------------------------
def word_limit_text(spec: Mapping[str, Any]) -> str:
    low, high = spec["min_words"], spec["max_words"]
    if low and high:
        return f"{low}-{high} words"
    return f"at least {low} words" if low else f"at most {high} words"


def validation_errors(settings: Settings, texts: Mapping[str, str], company: str, username: str = "") -> list[str]:
    """Reasons Generate must stay disabled (empty list = ready)."""
    errors: list[str] = []
    required = set(settings.required_fields())
    for spec in settings.writer_sections():
        text = (texts.get(spec["key"]) or "").strip()
        if not text:
            if spec["key"] in required:
                errors.append(f"{spec['label']} is required")
            continue
        if spec["min_words"] or spec["max_words"]:
            words = count_words(text)
            if words < spec["min_words"] or (spec["max_words"] and words > spec["max_words"]):
                errors.append(f"{spec['label']} must be {word_limit_text(spec)}")
    if FILE_NAME_FIELD in required and not company.strip():
        errors.append("File Name is required")
    if duplicate_files(settings, company):
        errors.append("A matching DOCX or PDF file already exists")
    return errors


# -- generation ---------------------------------------------------------------------------------
def build_content(settings: Settings, texts: Mapping[str, str]) -> ResumeContent:
    keywords_key = next((s["key"] for s in settings.writer_sections() if s["kind"] == "keywords"), None)
    plan = tuple(
        SectionSpec(key=s["key"], label=s["label"], kind=s["kind"], heading=s["heading"], show_heading=s["show_heading"])
        for s in settings.rendered_sections()
    )
    clean = {key: (text or "").strip() for key, text in texts.items()}
    return ResumeContent(
        name=settings.get("personal.name"), email=settings.get("personal.email"),
        phone=settings.get("personal.phone"), location=settings.get("personal.location"),
        tagline=settings.get("personal.tagline"),
        sections=clean, section_plan=plan,
        education_entries=tuple(settings.education_entries()),
        keywords_text=clean.get(keywords_key, "") if keywords_key else "",
        known_companies=tuple(settings.get("experience.known_companies")),
        author=settings.get("metadata.author"), subject=settings.get("metadata.subject"),
        title_template=settings.get("metadata.title_template"), keyword_count=settings.get("metadata.keyword_count"),
    )


def generate(ctx: WriterContext, texts: Mapping[str, str], company: str,
             typography: Optional[Mapping[str, Any]] = None) -> Path:
    """Validate, then write the resume to the output folder on this machine and return its path.

    ``typography`` (font_name, name_size, heading_size, body_size) defaults to the format's own values.
    """
    settings = ctx.settings
    errors = validation_errors(settings, texts, company, ctx.username)
    if errors:
        raise GenerationError("; ".join(errors))
    look = {**ctx.format_info, **(typography or {})}
    fmt = ResumeFormat(
        template_path=ctx.sample_path, font_name=str(look.get("font_name") or ""),
        name_size=int(look.get("name_size") or 0), heading_size=int(look.get("heading_size") or 0),
        body_size=int(look.get("body_size") or 0),
    )
    target = output_path(settings, company, ctx.username)
    try:
        return build_resume(build_content(settings, texts), fmt, target)
    except OSError as exc:
        raise GenerationError(f"Could not write {target}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - surface any generator problem as a message
        raise GenerationError(str(exc)) from exc
