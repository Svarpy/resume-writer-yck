"""Reverse of generation: the user-style text a sample document contains.

Used to verify fidelity (generate from the sample's own text and compare with the
sample) and to preview a format with realistic content.
"""

from __future__ import annotations

from resume_core.ooxml.analysis import DocumentAnalysis, Line, find_date
from resume_core.ooxml.xmlutil import paragraph_text


def _unit_text(line: Line) -> str:
    texts = [paragraph_text(p) for block in line.blocks for p in block.paragraphs]
    left_parts: list[str] = []
    date = ""
    for text in texts:
        span = find_date(text)
        if span and not date:
            date = text[span[0]:span[1]]
            before = text[: span[0]].strip(" \t|")
            if before:
                left_parts.append(before)
        elif text.strip():
            left_parts.append(text.strip())
    left = " ".join(left_parts)
    return f"{left}\t{date}" if date else left


def sample_sections(analysis: DocumentAnalysis) -> list[dict]:
    """Each section as ``{key, kind, heading, label, text}`` where ``text`` is user-style input."""
    out = []
    for region in analysis.regions:
        lines = []
        for line in region.lines:
            if line.role == "blank":
                continue
            if line.role == "unit":
                lines.append(_unit_text(line))
            elif line.role == "bullet" and not (line.labeled and region.kind == "skills"):
                lines.append("- " + line.text.strip().lstrip("•▸●○▪◦■□➢➤‣⁃*-– \t"))
            elif line.role == "bullet":
                lines.append(line.text.strip().lstrip("•▸●○▪◦■□➢➤‣⁃*-– \t"))
            else:
                lines.append(line.text.strip())
        text = "\n".join(lines)
        if region.kind == "education":
            # blank line between entries is only needed by the settings UI; keep one block
            text = text
        out.append({
            "key": region.key, "kind": region.kind, "heading": region.heading_text,
            "label": region.heading_text or region.key.title(), "text": text,
            "has_heading": region.has_heading,
        })
    return out
