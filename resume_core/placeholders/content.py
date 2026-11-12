"""From the Writer's text boxes to the structured data a template is filled with.

The templates are filled from plain nested data::

    {"name": ..., "email": ..., "phone": ..., "location": ..., "tagline": ...,
     "summary":    {"text": "..."},
     "skills":     {"items": [{"label": "Languages", "values": "Python, Go"}]},
     "experience": {"jobs": [{"company", "location", "dates",
                              "roles": [{"title", "dates", "bullets": [{"text"}]}], "bullets": [...]}]},
     "education":  {"degrees": [{"degree", "major", "institution", "location", "dates", "grade"}]},
     "<other>":    {"items": [{"text", "title", "dates"}]}}

The Writer (and MCP) deliver text; this module reads that text with ONE fixed grammar:

* skills            one ``Label: values`` line per skill (no label is fine);
* experience        ``Company | Location   dates`` starts a job, a short title line (with or without dates)
                    starts a role, every other line is a bullet of the current role;
* education         per degree: ``Degree in Major <tab>dates`` then ``Institution, City | GPA: x``;
                    a blank line separates degrees;
* any other list    one item per line.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from resume_core.placeholders.dates import DATE_RANGE, find_date
from resume_core.render.parse import (
    clean_lines,
    detect_known_company,
    fallback_role_date,
    looks_like_role_line,
    normalize_date_text,
    split_known_company_line,
    strip_bullet_marker,
)

_LABEL = re.compile(r"^\s*([^:\n]{1,60}?)\s*:\s*(\S.*)$")


def split_dated(line: str) -> Optional[tuple[str, str]]:
    """``(left text, date)`` of ``Acme | Remote   Jan 2020 - Present``, or None.

    The date has to close the line (a short ``| GPA 4.0`` style annotation may follow), so a sentence
    that merely mentions a range ("... across 2023-2024, recognised for ...") is never a dated heading.
    """
    text = line.strip()
    if "\t" in text:
        left, right = text.rsplit("\t", 1)
        span = find_date(right)
        if span and left.strip():
            return left.strip().rstrip(" |,-–—"), right[span[0]:span[1]]
    for match in reversed(list(DATE_RANGE.finditer(text))):
        left = text[: match.start()].strip()
        rest = text[match.end():].strip()
        if not left:
            continue
        if rest and not (rest[0] in "|(" and len(rest.split()) <= 6):
            continue
        if len(left.split()) > 16 or left.endswith("."):
            continue
        return left.rstrip(" |,-–—"), match.group()
    return None


def _company_parts(left: str) -> tuple[str, str]:
    parts = [p.strip() for p in re.split(r"\s*\|\s*", left) if p.strip()]
    if not parts:
        return left.strip(), ""
    return parts[0], ", ".join(parts[1:])


# --------------------------------------------------------------------------
# One section at a time
# --------------------------------------------------------------------------


def paragraph_data(text: str) -> dict[str, Any]:
    return {"text": " ".join(line.strip() for line in clean_lines(text) if line.strip())}


def skills_data(text: str) -> dict[str, Any]:
    items = []
    for line in clean_lines(text):
        line = strip_bullet_marker(line.strip())
        if not line:
            continue
        match = _LABEL.match(line)
        label, values = (match.group(1), match.group(2)) if match else ("", line)
        items.append({"label": label, "values": values.strip(), "text": line})
    return {"items": items}


def list_data(text: str) -> dict[str, Any]:
    items = []
    for line in clean_lines(text):
        line = strip_bullet_marker(line.strip())
        if not line:
            continue
        dated = split_dated(line)
        items.append({"text": line, "title": dated[0] if dated else line,
                      "dates": normalize_date_text(dated[1]) if dated else ""})
    return {"items": items}


def experience_data(text: str, known_companies=()) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    job: Optional[dict[str, Any]] = None
    company_index: Optional[int] = None
    role_count: dict[Optional[int], int] = {}

    def new_job(left: str, dates: str, index: Optional[int] = None) -> dict[str, Any]:
        company, location = _company_parts(left)
        created = {"company": company, "location": location, "dates": normalize_date_text(dates) if dates else "",
                   "roles": [], "bullets": []}
        jobs.append(created)
        return created

    def new_role(title: str, dates: str) -> None:
        nonlocal job
        if job is None:
            job = new_job("", "")
        job["roles"].append({"title": title.strip(), "dates": normalize_date_text(dates) if dates else "",
                             "bullets": []})

    for raw in clean_lines(text):
        stripped = raw.strip()
        if not stripped:
            continue
        clean = strip_bullet_marker(stripped)
        marked = clean != stripped
        dated = split_dated(clean)
        if dated:
            left, date = dated
            detected = detect_known_company(left, known_companies)
            if detected is not None:
                company_index = detected
                role_count.setdefault(detected, 0)
                job = new_job(left, date)
            elif looks_like_role_line(left):
                if fallback_role_date(company_index, role_count.get(company_index, 0), known_companies):
                    role_count[company_index] = role_count.get(company_index, 0) + 1
                new_role(left, date)
            else:
                job = new_job(left, date)
            continue
        known = split_known_company_line(clean, known_companies)
        if known:
            left, date, company_index = known
            role_count.setdefault(company_index, 0)
            job = new_job(left, date)
            continue
        if not marked and looks_like_role_line(clean):
            index = role_count.get(company_index, 0)
            role_date = fallback_role_date(company_index, index, known_companies) or ""
            if role_date:
                role_count[company_index] = index + 1
            new_role(clean, role_date)
            continue
        # a bullet of the current role (or of the job itself when it has no role yet)
        if job is None:
            job = new_job("", "")
        target = job["roles"][-1]["bullets"] if job["roles"] else job["bullets"]
        target.append({"text": clean})
    return {"jobs": jobs}


_DEGREE_SPLIT = re.compile(r"\s+in\s+|\s*[,–—]\s+|\s+-\s+", re.IGNORECASE)


def education_data(entries, has_major: bool = True, has_location: bool = True,
                   grade_label: bool = False) -> dict[str, Any]:
    degrees = []
    for entry in entries:
        for chunk in re.split(r"\n\s*\n", (entry or "").strip()):
            lines = [l.strip() for l in clean_lines(chunk) if l.strip()]
            if not lines:
                continue
            first = lines[0]
            dated = split_dated(first)
            left, dates = (dated[0], normalize_date_text(dated[1])) if dated else (first, "")
            degree, major = left, ""
            if has_major:
                parts = _DEGREE_SPLIT.split(left, maxsplit=1)
                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                    degree, major = parts[0].strip(), parts[1].strip()
            institution, location, grade = "", "", ""
            if len(lines) > 1:
                pieces = [p.strip() for p in re.split(r"\s*\|\s*", lines[1]) if p.strip()]
                school = pieces[0] if pieces else ""
                if len(pieces) > 1:
                    grade = " | ".join(pieces[1:])
                    label = re.match(r"^[A-Za-z .]{2,20}:\s*(.+)$", grade)
                    if grade_label and label:
                        grade = label.group(1)
                institution = school
                if has_location and "," in school:
                    head, _, tail = school.rpartition(",")
                    if len(tail.split()) <= 3 and head.strip():
                        institution, location = head.strip(), tail.strip()
            degrees.append({"degree": degree, "major": major, "institution": institution,
                            "location": location, "dates": dates, "grade": grade})
    return {"degrees": degrees}


# --------------------------------------------------------------------------
# The whole resume
# --------------------------------------------------------------------------


def build_data(content, shape: Mapping[str, Any]) -> dict[str, Any]:
    """Structured template data from a ``ResumeContent`` (text per section) and the template's ``shape``.

    ``shape`` is ``TemplateInfo.shape``: for each section its kind and the fields its blocks use, so
    text is parsed only as finely as the template can show it.
    """
    data: dict[str, Any] = {
        "name": content.name.strip(), "tagline": (getattr(content, "tagline", "") or "").strip(),
        "email": content.email.strip(), "phone": content.phone.strip(), "location": content.location.strip(),
    }
    for key, section in shape.items():
        kind = section["kind"]
        fields = section["fields"]
        if kind == "education":
            entries = [e for e in content.education_entries if (e or "").strip()]
            if entries:
                data[key] = education_data(
                    entries, has_major="major" in fields.get("degrees", ()),
                    has_location="location" in fields.get("degrees", ()),
                    grade_label=section.get("grade_label", False))
            continue
        text = (content.text_for(key) or "").strip()
        if not text:
            continue
        if kind == "paragraph":
            data[key] = paragraph_data(text)
        elif kind == "skills":
            data[key] = skills_data(text)
        elif kind == "experience":
            data[key] = _fit_experience(experience_data(text, content.known_companies), fields)
        else:
            data[key] = list_data(text)
    return data


def _fit_experience(data: dict[str, Any], fields: Mapping[str, tuple]) -> dict[str, Any]:
    """Shape jobs the way the template lays them out (roles or not, which dates are shown where)."""
    has_roles = "roles" in fields
    job_fields = set(fields.get("jobs", ()))
    role_fields = set(fields.get("roles", ()))
    for job in data["jobs"]:
        if has_roles:
            if not job["roles"]:
                job["roles"] = [{"title": "", "dates": "", "bullets": job["bullets"]}]
                job["bullets"] = []
            elif job["bullets"]:
                job["roles"][0]["bullets"] = [*job["bullets"], *job["roles"][0]["bullets"]]
                job["bullets"] = []
            if "dates" not in job_fields and "dates" in role_fields and job["dates"]:
                first = job["roles"][0]
                if not first["dates"]:
                    first["dates"] = job["dates"]      # the company's dates move to its first role line
        else:
            for role in job["roles"]:
                job["bullets"].extend(role["bullets"])
            job["roles"] = []
    return data
