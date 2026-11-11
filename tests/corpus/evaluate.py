"""Run one corpus resume through the analyser and the generator and report everything that is wrong."""

from __future__ import annotations

import io
import re
import tempfile
import zipfile
from pathlib import Path

from docx import Document
from lxml import etree

from resume_core.ooxml.analysis import analyze_document
from resume_core.ooxml.xmlutil import PPR, RPR, iter_paragraphs, paragraph_text, text_items
from resume_core.render import ResumeContent, ResumeFormat, SectionSpec
from resume_core.render.template import build_resume_from_template
from resume_core.sanitize import sanitize_sample
from tests.corpus.builders import EMAIL, NAME, Spec

# builder kind -> analyser kinds accepted
EXPECTED_KINDS = {
    "paragraph": {"paragraph"}, "skills": {"skills"}, "experience": {"experience"}, "education": {"education"},
    "projects": {"bullets", "experience"}, "bullets": {"bullets"}, "inline": {"paragraph", "bullets"},
    "declaration": {"paragraph"}, "references": {"paragraph"},
}
USER_NAME, USER_EMAIL, USER_PHONE, USER_CITY = "Usrfirst Usrlast", "usr.mail@usrmail.test", "+1 555 010 7777", "Usrtown, Usrland"


def user_texts(kind: str, key: str) -> str:
    tag = key.title().replace("_", "")
    if kind == "paragraph":
        return f"Usr{tag} paragraph one describing delivery of usrresults.\nUsr{tag} paragraph two about usrteamwork."
    if kind == "skills":
        return f"Usr{tag}A: Go, Rust, usrlang\nUsr{tag}B: git, make, usrtool\nUsr{tag}C: AWS, GCP, usrcloud\nUsr{tag}D: usrdb1, usrdb2"
    if kind == "experience":
        return "\n".join([
            f"UsrCorp{tag}A | UsrCityA   March 2022 - Present", f"Usr Senior Developer {tag}   March 2022 - Present",
            f"- Usr{tag} delivered usrfeature alpha with measurable impact.", f"- Usr{tag} improved usrmetric beta by 40%.",
            f"UsrCorp{tag}B | UsrCityB   June 2019 - February 2022", f"Usr Developer {tag}   June 2019 - February 2022",
            f"- Usr{tag} built usrservice gamma used by many teams.", f"- Usr{tag} mentored usrinterns on delta.",
            f"UsrCorp{tag}C | UsrCityC   2017 - 2019", f"Usr Intern {tag}   2017 - 2019", f"- Usr{tag} wrote usrtests epsilon.",
        ])
    return f"- Usr{tag} item one about usralpha\n- Usr{tag} item two about usrbeta\n- Usr{tag} item three about usrgamma"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\t", " ")).strip().casefold()


def _fingerprint(paragraph) -> tuple:
    items = [i for i in text_items(paragraph) if i.kind == "t" and (i.element.text or "").strip()]
    canon = lambda el: "" if el is None else re.sub(r' w:rsid\w*="[^"]*"| xmlns:\w+="[^"]*"', "", etree.tostring(el).decode())  # noqa: E731
    return canon(paragraph.find(PPR)), canon(items[0].run.find(RPR) if items else None)


def all_text(document) -> str:
    return "\n".join(_norm(paragraph_text(p)) for p in iter_paragraphs(document.element.body))


def evaluate(spec: Spec, path: Path) -> list[str]:
    issues: list[str] = []
    sample = Document(str(path))
    analysis = analyze_document(sample)

    # ---- analysis -----------------------------------------------------------------------------------------
    if analysis.name is None or NAME.casefold() not in _norm(analysis.name.text):
        issues.append(f"name not detected (got {analysis.name.text if analysis.name else None!r})")
    if analysis.contact is None or EMAIL.casefold() not in _norm(analysis.contact.text):
        issues.append(f"contact line not detected (got {analysis.contact.text[:40] if analysis.contact else None!r})")
    expected = [(e[0], e[1]) for e in spec.sections]
    if spec.layout == "two_col":  # reading order: the table's left column comes first
        expected = [(e[0], e[1]) for e in spec.sections if len(e) > 2] + [(e[0], e[1]) for e in spec.sections if len(e) <= 2]
    found = [(r.heading_text, r.kind) for r in analysis.regions]
    if len(found) != len(expected):
        issues.append(f"sections: expected {[t for t, _k in expected]} found {[t for t, _k in found]}")
    from resume_core.ooxml.analysis import canonical_key, heading_core

    for (title, kind), (heading, got), region in zip(expected, found, analysis.regions):
        wanted_key = canonical_key(title)
        if wanted_key and region.key != wanted_key:
            issues.append(f"heading {title!r} got key {region.key!r}, expected {wanted_key!r}")
        if heading_core(heading) != _norm(title):
            issues.append(f"heading {title!r} read as {heading!r}")
        elif got not in EXPECTED_KINDS[kind]:
            issues.append(f"section {title!r}: kind {got!r}, expected one of {sorted(EXPECTED_KINDS[kind])}")
    if issues:
        return issues  # generation results would be meaningless

    # ---- generation with different content ----------------------------------------------------------------------------
    plan, sections, education, tokens = [], {}, [], []
    for region in analysis.regions:
        plan.append(SectionSpec(region.key, region.heading_text or region.key, region.kind))
        if region.kind == "education":
            education = ["Bachelor of Usrdegree\tAugust 2015 – May 2019\nUsruniversity University, UsrCity",
                         "Higher Secondary Usrschool\t2013 – 2015\nUsrschool College"]
            tokens += ["usrdegree", "usruniversity", "usrschool"]
        else:
            sections[region.key] = user_texts(region.kind, region.key)
            tokens += re.findall(r"usr\w+|Usr\w+", sections[region.key])
    content = ResumeContent(
        name=USER_NAME, email=USER_EMAIL, phone=USER_PHONE, location=USER_CITY, sections=sections,
        section_plan=tuple(plan), education_entries=tuple(education),
    )
    out = Path(tempfile.mkdtemp()) / "out.docx"
    try:
        build_resume_from_template(content, ResumeFormat(template_path=path), out)
        result = Document(str(out))
    except Exception as exc:  # noqa: BLE001
        return [f"generation failed: {type(exc).__name__}: {exc}"]
    text = all_text(result)

    if any(r.kind == "experience" for r in analysis.regions) and "usrcorp" not in text.replace(" ", "").lower():
        issues.append("company names were lost")
    for token in sorted({t.casefold() for t in tokens}):
        if token not in text:
            issues.append(f"user content missing: {token}")
    for needed in (USER_NAME, USER_EMAIL, USER_PHONE, USER_CITY):
        if needed.casefold() not in text:
            issues.append(f"header value missing: {needed}")
    archive = zipfile.ZipFile(out)
    for part in archive.namelist():
        if part.endswith((".xml", ".rels")) and "styles" not in part and "theme" not in part and "fontTable" not in part:
            if re.search(rb"zq", archive.read(part), re.IGNORECASE):
                issues.append(f"sample text left in {part}")
    last = -1
    for region in analysis.regions:  # headings in order
        index = text.find(_norm(region.heading_text), last + 1) if region.has_heading else last
        if index < 0:
            issues.append(f"heading {region.heading_text!r} missing or out of order")
        else:
            last = max(last, index)
    sample_prints = {_fingerprint(p) for p in iter_paragraphs(sample.element.body)}
    invented = [paragraph_text(p)[:30] for p in iter_paragraphs(result.element.body) if _fingerprint(p) not in sample_prints]
    if invented:
        issues.append(f"{len(invented)} paragraphs with formatting not found in the sample, e.g. {invented[:3]}")
    if len(result.tables) < len(sample.tables) - 6 and sample.tables:  # content tables may multiply; layout tables must stay
        issues.append(f"tables lost: {len(sample.tables)} -> {len(result.tables)}")

    issues += _strict_checks(spec, analysis, plan, sections, result, text, out)
    issues += _variant_checks(spec, path, analysis)

    # ---- sanitising ------------------------------------------------------------------------------------------------------------
    cleaned, ok = sanitize_sample(path.read_bytes())
    if not ok:
        issues.append("sanitising refused (original would be stored)")
    else:
        clean_path = Path(tempfile.mkdtemp()) / "clean.docx"
        clean_path.write_bytes(cleaned)
        out2 = Path(tempfile.mkdtemp()) / "out2.docx"
        build_resume_from_template(content, ResumeFormat(template_path=clean_path), out2)
        if all_text(Document(str(out2))) != text:
            issues.append("output from the sanitised sample differs from the original's")
        leak = [part for part in zipfile.ZipFile(io.BytesIO(cleaned)).namelist()
                if part.endswith((".xml", ".rels")) and re.search(rb"zq", zipfile.ZipFile(io.BytesIO(cleaned)).read(part), re.IGNORECASE)
                and "styles" not in part and "theme" not in part and "fontTable" not in part]
        if leak:
            issues.append(f"sanitised sample still holds sample text in {leak}")
    return issues


DATE_TOKENS = ("march 2022 – present", "june 2019 – february 2022", "2017 – 2019")


def _strict_checks(spec, analysis, plan, sections, result, text, out) -> list[str]:
    issues: list[str] = []
    # 1. every section's content sits under its own heading (before the next heading)
    positions = []
    for region in analysis.regions:
        if region.has_heading:
            positions.append((text.find(_norm(region.heading_text)), region))
    for index, (start, region) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(text)
        if region.kind == "education":
            wanted = ["usrdegree", "usruniversity", "usrschool"]
        else:
            wanted = sorted({t.casefold() for t in re.findall(r"usr\w+|Usr\w+", sections.get(region.key, ""))})
        for token in wanted:
            where = text.find(token, start + 1)
            if where < 0 or where >= end:
                issues.append(f"{token} is not under its heading {region.heading_text!r}")
                break
    # 2. dates keep the sample's punctuation and are written for every job
    experience = [r for r in analysis.regions if r.kind == "experience"]
    if experience and spec.dates in ("tab", "table", "nextline", "paren", "pipe", "comma", "left"):
        for token in DATE_TOKENS:
            if token not in text:
                issues.append(f"date missing: {token}")
        if spec.dates == "paren" and "(march 2022 – present)" not in text:
            issues.append("date lost its parentheses")
        if spec.dates == "pipe" and "| march 2022 – present" not in text:
            issues.append("date lost its '|' separator")
        if spec.dates == "comma" and ", march 2022 – present" not in text:
            issues.append("date lost its ',' separator")
    # 3. skills table keeps one row per skill line
    skills = next((r for r in analysis.regions if r.kind == "skills"), None)
    if skills is not None and spec.skills == "table":
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        rows = 0
        for table in result.element.body.iter(ns + "tbl"):  # includes tables nested in cells
            if "usrskillsa" in _norm("".join(t.text or "" for t in table.iter(ns + "t"))):
                rows = max(rows, len(table.findall(ns + "tr")))
        if rows != 4:
            issues.append(f"skills table has {rows} rows, expected 4")
    # 4. no empty paragraphs piling up (more than 2 in a row) that the sample did not have
    run = longest = 0
    for paragraph in iter_paragraphs(result.element.body):
        run = run + 1 if not paragraph_text(paragraph).strip() else 0
        longest = max(longest, run)
    if longest > 3:
        issues.append(f"{longest} empty paragraphs in a row")
    # 5. a generated resume is a valid sample again with the same sections
    again = analyze_document(result)
    if [(r.key, r.kind) for r in again.regions] != [(r.key, r.kind) for r in analysis.regions]:
        issues.append(f"generated resume analyses differently: {[(r.key, r.kind) for r in again.regions]}")
    return issues


def _variant_checks(spec, path, analysis) -> list[str]:
    """Other content shapes: minimal (empty sections omitted) and text with special characters."""
    issues: list[str] = []
    first = analysis.regions[0]
    # minimal: only the first section filled
    plan = tuple(SectionSpec(r.key, r.heading_text or r.key, r.kind) for r in analysis.regions)
    content = ResumeContent(name="Min Imal", email="min@imal.test", phone="", location="", section_plan=plan,
                            sections={first.key: "Only one usrline here."} if first.kind != "education" else {},
                            education_entries=("UsrOnly Degree\tMay 2020 – May 2024",) if first.kind == "education" else ())
    out = Path(tempfile.mkdtemp()) / "min.docx"
    try:
        build_resume_from_template(content, ResumeFormat(template_path=path), out)
    except Exception as exc:  # noqa: BLE001
        return [f"minimal content failed: {type(exc).__name__}: {exc}"]
    text = all_text(Document(str(out)))
    for region in analysis.regions[1:]:
        if region.has_heading and _norm(region.heading_text) in text:
            issues.append(f"empty section {region.heading_text!r} still written")
    if "min@imal.test" not in text or "zq" in text:
        issues.append("minimal output has wrong header values or sample text")
    # special characters and long lines
    special = 'Cost & benefit <analysis> with "quotes", O\'Brien, Zoë Müller – 日本語 ✅ ' + "usrlong " * 60
    sections = {r.key: (special if r.kind in ("paragraph", "bullets") else "") for r in analysis.regions}
    texts = {k: v for k, v in sections.items() if v}
    if texts:
        content = ResumeContent(name="Zoë O'Brien-Müller", email="zoe@x.test", phone="+44 20 7946 0000", location="Zürich", section_plan=plan, sections=texts)
        out = Path(tempfile.mkdtemp()) / "special.docx"
        try:
            build_resume_from_template(content, ResumeFormat(template_path=path), out)
            reopened = Document(str(out))
            joined = all_text(reopened)
            if "cost & benefit <analysis>" not in joined or "日本語 ✅" not in joined or "zoë o'brien-müller" not in joined:
                issues.append("special characters were lost or changed")
        except Exception as exc:  # noqa: BLE001
            issues.append(f"special characters failed: {type(exc).__name__}: {exc}")
    return issues
