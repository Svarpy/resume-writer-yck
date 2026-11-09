"""Text and experience-line parsing helpers for resume generation."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional, Tuple

from resume_writer.constants import (
    COMPANY_ALIASES,
    COMPANY_DATE_DEFAULTS,
    DATE_RANGE_RE,
    ROLE_DATE_DEFAULTS_BY_COMPANY,
)


def default_output_filename() -> str:
    today = date.today()
    return f"YcKResumeXXX{today:%d%b}.docx"


def default_output_filename_for(company_part: str = "") -> str:
    today = date.today()
    clean_part = re.sub(r"[^A-Za-z0-9_-]+", "", company_part.strip())
    return f"YcKResume{clean_part or 'XXX'}{today:%d%b}.docx"


def find_matching_output_files(output_dir: Path, name_part: str, *, include_applied: bool = True) -> list[Path]:
    clean_part = re.sub(r"[^A-Za-z0-9_-]+", "", name_part.strip())
    if not clean_part or not output_dir.exists() or not output_dir.is_dir():
        return []
    needle = clean_part.casefold()
    matches = []
    search_dirs = [output_dir]
    applied_dir = output_dir / "#applied"
    if include_applied and applied_dir.exists() and applied_dir.is_dir():
        search_dirs.append(applied_dir)
    for search_dir in search_dirs:
        for path in search_dir.iterdir():
            if path.suffix.casefold() not in {".docx", ".pdf"}:
                continue
            if needle in path.name.casefold():
                matches.append(path)
    return sorted(matches, key=lambda path: path.name.casefold())



def normalize_experience_bullet_text(text: str) -> str:
    return re.sub(r"\s+—\s+", ", ", text.strip())


def clean_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def split_keywords(text: str) -> list[str]:
    parts = re.split(r"[,;\n]", text)
    return [part.strip() for part in parts if part.strip()][:5]


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def phone_hyperlink(phone: str) -> str:
    compact = re.sub(r"\s+", "%20", phone.strip())
    return f"tel:{compact}"


def normalize_date_text(text: str) -> str:
    return re.sub(r"\s*(?:-|–|—|to)\s*", " – ", text.strip(), flags=re.IGNORECASE)


def normalize_dated_left_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    return re.sub(r"\s*\|\s*", " | ", normalized).strip(" |,-")


def split_right_side_date(left: str, right: str) -> Optional[Tuple[str, str]]:
    match = DATE_RANGE_RE.search(right)
    if not match:
        return None
    right_prefix = normalize_dated_left_text(right[: match.start()])
    left_parts = [normalize_dated_left_text(left)]
    if right_prefix:
        left_parts.append(right_prefix)
    return " ".join(part for part in left_parts if part), normalize_date_text(match.group(0))


def split_dated_line(line: str) -> Optional[Tuple[str, str]]:
    stripped = line.strip()

    if "\t" in stripped:
        left, right = stripped.rsplit("\t", 1)
        dated = split_right_side_date(left, right)
        if dated:
            return dated

    if "|" in stripped:
        left, right = stripped.rsplit("|", 1)
        dated = split_right_side_date(left, right)
        if dated:
            return dated

    match = DATE_RANGE_RE.search(stripped)
    if match and match.start() > 0:
        left = normalize_dated_left_text(stripped[: match.start()])
        if left:
            return left, normalize_date_text(match.group(0))

    return None


def detect_known_company(line: str) -> Optional[str]:
    normalized = re.sub(r"\s+", " ", line.strip())
    normalized_lower = normalized.lower()
    if DATE_RANGE_RE.search(normalized):
        return None
    for company_key, aliases in COMPANY_ALIASES.items():
        if any(normalized_lower.startswith(alias) for alias in aliases):
            return company_key
    return None


def split_known_company_line(line: str) -> Optional[Tuple[str, str, str]]:
    company_key = detect_known_company(line)
    if not company_key:
        return None
    left = re.sub(r"\s+", " ", line.strip()).strip(" |,-")
    left = re.sub(r"\s*\|\s*", " | ", left)
    return left, COMPANY_DATE_DEFAULTS[company_key], company_key


def fallback_role_date(company_key: Optional[str], role_index: int) -> Optional[str]:
    if not company_key:
        return None
    dates = ROLE_DATE_DEFAULTS_BY_COMPANY.get(company_key, ())
    if not dates:
        return None
    return dates[min(role_index, len(dates) - 1)]


def looks_like_role_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.endswith("."):
        return False
    if len(stripped.split()) > 10:
        return False
    if re.search(r"\b(built|created|designed|developed|implemented|improved|reduced|delivered|managed|maintained)\b", stripped, re.IGNORECASE):
        return False
    if re.search(r"\b(engineer|developer|analyst|architect|consultant|intern|lead|manager|specialist|associate)\b", stripped, re.IGNORECASE):
        return True
    return False
