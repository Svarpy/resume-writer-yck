"""Text and experience-line parsing helpers for resume generation."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from resume_core.constants import DATE_RANGE_RE

# One "known company" entry (from Settings > Experience Parsing):
# {"name": str, "aliases": [str], "default_date": str, "role_dates": [str]}
KnownCompanies = Sequence[Mapping[str, Any]]

DEFAULT_FILENAME_TEMPLATE = "Resume{company}{date}"
DEFAULT_FILENAME_PLACEHOLDER = "XXX"
DEFAULT_FILENAME_DATE_FORMAT = "%d%b"


def _filename_token(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", text.strip())


def clean_company_part(company_part: str) -> str:
    """The File Name field value reduced to filename-safe characters."""
    return _filename_token(company_part)


def build_output_filename(
    company_part: str = "",
    *,
    template: str = DEFAULT_FILENAME_TEMPLATE,
    placeholder: str = DEFAULT_FILENAME_PLACEHOLDER,
    date_format: str = DEFAULT_FILENAME_DATE_FORMAT,
    name: str = "",
    username: str = "",
    today: Optional[date] = None,
) -> str:
    """Expand ``template`` into a ``.docx`` file name.

    Placeholders: ``{company}`` (cleaned File Name field, or ``placeholder`` when
    empty), ``{date}`` (``date_format`` applied to ``today``), ``{name}`` and
    ``{username}``.
    """
    day = today or date.today()
    values = {
        "company": _filename_token(company_part) or _filename_token(placeholder) or "XXX",
        "date": re.sub(r'[\\/:*?"<>|]+', "", day.strftime(date_format)).strip(),
        "name": _filename_token(name.replace(" ", "")),
        "username": _filename_token(username),
    }
    text = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template)
    text = re.sub(r'[\\/:*?"<>|]+', "", text).strip(" .")
    return f"{text or 'Resume'}.docx"


def default_output_filename(**kwargs: Any) -> str:
    return build_output_filename("", **kwargs)


def default_output_filename_for(company_part: str = "", **kwargs: Any) -> str:
    return build_output_filename(company_part, **kwargs)


def find_duplicate_files(
    directories: Iterable[Path],
    name_part: str,
    *,
    extensions: Iterable[str] = (".docx", ".pdf"),
    case_sensitive: bool = False,
) -> list[Path]:
    """Files in ``directories`` whose name contains the cleaned ``name_part``.

    Only files with one of ``extensions`` are considered. Missing folders are
    ignored; a folder listed twice is only searched once.
    """
    clean_part = _filename_token(name_part)
    if not clean_part:
        return []
    wanted = {ext.strip().casefold() if ext.strip().startswith(".") else "." + ext.strip().casefold()
              for ext in extensions if ext.strip()}
    needle = clean_part if case_sensitive else clean_part.casefold()
    matches: dict[str, Path] = {}
    for directory in directories:
        try:
            if not directory.is_dir():
                continue
            entries = list(directory.iterdir())
        except OSError:
            continue
        for path in entries:
            if not path.is_file() or path.suffix.casefold() not in wanted:
                continue
            haystack = path.name if case_sensitive else path.name.casefold()
            if needle in haystack:
                matches[str(path.resolve())] = path
    return sorted(matches.values(), key=lambda path: (path.name.casefold(), str(path)))


def strip_bullet_marker(line: str) -> str:
    return re.sub(r"^(?:[-*]|\u2022)\s+", "", line.strip())


def normalize_experience_bullet_text(text: str) -> str:
    return re.sub(r"\s+—\s+", ", ", text.strip())


def clean_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def split_keywords(text: str, limit: int = 5) -> list[str]:
    parts = re.split(r"[,;\n]", text)
    return [part.strip() for part in parts if part.strip()][: max(0, limit)]


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def phone_hyperlink(phone: str) -> str:
    compact = re.sub(r"\s+", "%20", phone.strip())
    return f"tel:{compact}"


def normalize_date_text(text: str) -> str:
    # "to" only counts as a separator when it is a word of its own ("October" must survive).
    return re.sub(r"\s*(?:-|–|—)\s*|\s+to\s+", " – ", text.strip(), flags=re.IGNORECASE)


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


def detect_known_company(line: str, companies: KnownCompanies = ()) -> Optional[int]:
    """Index of the configured company whose alias ``line`` starts with, if any."""
    normalized = re.sub(r"\s+", " ", line.strip())
    normalized_lower = normalized.lower()
    if DATE_RANGE_RE.search(normalized):
        return None
    for index, company in enumerate(companies):
        for alias in company.get("aliases", ()):
            alias = alias.strip().lower()
            if alias and normalized_lower.startswith(alias):
                return index
    return None


def split_known_company_line(line: str, companies: KnownCompanies = ()) -> Optional[Tuple[str, str, int]]:
    """``(left text, fallback date, company index)`` for an undated known-company line."""
    company_index = detect_known_company(line, companies)
    if company_index is None:
        return None
    left = re.sub(r"\s+", " ", line.strip()).strip(" |,-")
    left = re.sub(r"\s*\|\s*", " | ", left)
    return left, str(companies[company_index].get("default_date", "")).strip(), company_index


def fallback_role_date(company_index: Optional[int], role_index: int, companies: KnownCompanies = ()) -> Optional[str]:
    if company_index is None or not 0 <= company_index < len(companies):
        return None
    dates = [str(d).strip() for d in companies[company_index].get("role_dates", ()) if str(d).strip()]
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
