"""Resume content / format models used by the generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple



@dataclass(frozen=True)
class ResumeFormat:
    """What to generate with: the sample document plus the font and size choices.

    Page setup, styles, headings and layout always come from the sample itself; the font and
    sizes are applied on top (a value of 0 / "" leaves that property as the sample has it).
    """

    template_path: Optional[Path] = None
    font_name: str = ""
    name_size: int = 0
    heading_size: int = 0
    body_size: int = 0


@dataclass(frozen=True)
class SectionSpec:
    """One resume section to write, in document order (from Settings > Resume Sections)."""

    key: str
    label: str
    kind: str  # paragraph | skills | experience | bullets | education
    heading: str = ""  # blank → selected format's heading, then the label in capitals
    show_heading: bool = True


@dataclass(frozen=True)
class ResumeContent:
    name: str
    email: str
    phone: str
    location: str
    summary: str = ""
    skills: str = ""
    experience: str = ""
    certifications: str = ""
    top_skills: str = ""
    education_entries: Tuple[str, ...] = ()
    # --- dynamic sections (Settings > Resume Sections) -----------------------
    # key → pasted text. Keys not present fall back to the legacy fields above.
    sections: Mapping[str, str] = field(default_factory=dict)
    # Ordered plan of sections to render. Empty → legacy five-section behaviour
    # driven by the selected format's structure.
    section_plan: Tuple[SectionSpec, ...] = ()
    # Text of the keywords section (DOCX keywords metadata), when it is not top_skills.
    keywords_text: str = ""
    # Settings > Experience Parsing
    known_companies: Tuple[Mapping[str, Any], ...] = ()
    tagline: str = ""  # optional line under the name (Settings > Personal Details)
    # Settings > Metadata
    author: str = ""
    subject: str = ""
    title_template: str = ""
    keyword_count: int = 5

    def text_for(self, key: str) -> str:
        if key in self.sections:
            return self.sections[key]
        return getattr(self, key, "") if key in _LEGACY_TEXT_KEYS else ""

    def keyword_source(self) -> str:
        return self.keywords_text or self.top_skills


_LEGACY_TEXT_KEYS = ("summary", "skills", "experience", "certifications", "top_skills")
